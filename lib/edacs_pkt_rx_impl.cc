/* -*- c++ -*- */
/* 
 * Copyright 2013 <+YOU OR YOUR COMPANY+>.
 * 
 * This is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3, or (at your option)
 * any later version.
 * 
 * This software is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this software; see the file COPYING.  If not, write to
 * the Free Software Foundation, Inc., 51 Franklin Street,
 * Boston, MA 02110-1301, USA.
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include <gnuradio/io_signature.h>
#include <gnuradio/msg_queue.h>
#include <gnuradio/tags.h>
#include "edacs_pkt_rx_impl.h"

#define DEBUG 1

namespace gr {
  namespace scanner {

    edacs_pkt_rx::sptr
    edacs_pkt_rx::make(gr::msg_queue::sptr queue)
    {
      return gnuradio::get_initial_sptr
        (new edacs_pkt_rx_impl(queue));
    }

    /*
     * The private constructor
     */
    edacs_pkt_rx_impl::edacs_pkt_rx_impl(gr::msg_queue::sptr queue)
      : gr::sync_block("edacs_pkt_rx",
              gr::io_signature::make(1, 1, sizeof(char)),
              gr::io_signature::make(0, 0, 0)),
        d_queue(queue)
    {
        set_output_multiple(288*2);
    }

    /*
     * Our virtual destructor.
     */
    edacs_pkt_rx_impl::~edacs_pkt_rx_impl()
    {
    }

    static bool crc(uint64_t pkt) {
        //extract data from checksum
        uint16_t checksum = pkt | 0xFFF;
        uint64_t data = pkt >> 12;
        uint16_t poly = 0x7D7;
        uint16_t crc = 0;
        return 1; //TODO HALP
    }

    int
    edacs_pkt_rx_impl::work(int noutput_items,
                            gr_vector_const_void_star &input_items,
                            gr_vector_void_star &output_items)
    {
        const char *in = (const char *) input_items[0];

        // make sure we have enough items to process a whole pkt
        const float nitems = noutput_items - 240;

        std::vector<gr::tag_t> preamble_tags;
        uint64_t abs_sample_cnt = nitems_read(0);
        get_tags_in_range(preamble_tags, 0, abs_sample_cnt, abs_sample_cnt + nitems, pmt::string_to_symbol("edacs_preamble"));
        if(preamble_tags.size() == 0) return nitems; //sad trombone
        std::vector<gr::tag_t>::iterator tag_iter;
        for(tag_iter = preamble_tags.begin(); tag_iter != preamble_tags.end(); tag_iter++) {
            uint64_t i = tag_iter->offset - abs_sample_cnt; //48 is the preamble length
            assert(i < abs_sample_count + noutput_items); //just to be safe
            //EDACS packets are weird.
            //First of all, there's two packets per block.
            //Secondly, there are three 40-bit copies to each packet.
            //The second one is inverted. This is dumb.
            uint64_t pkts[2][3];
            memset(pkts, 0x00, sizeof(uint64_t) * 6);
            for(int l=0; l<2; l++) {
                for(int k=0; k<3; k++) {
                    for(int j=0; j<40; j++) {
                        pkts[l][k] <<= 1;
                        pkts[l][k] |= in[i++];
                    }
                }
                //invert the second one
                pkts[l][1] ^= uint64_t(0xFFFFFFFFFF);
                //compare them all
                bool ok12 = (pkts[l][0] == pkts[l][1]);
                bool ok23 = (pkts[l][1] == pkts[l][2]);
                bool ok13 = (pkts[l][0] == pkts[l][2]);
                //we just want two of the same in order to call it good.
                if(not (ok12 or ok23 or ok13)) continue; //garbage
                uint64_t ok = (ok12 or ok13) ? pkts[l][0] : pkts[l][2];
                //now check CRC
                if(not crc(ok)) continue;
                //now push that message out the queue.
//                pmt::pmt_t p = pmt::mp(ok);

                std::stringstream payload;
                payload.str("");
                payload << std::hex << ok;
                gr::message::sptr msg = gr::message::make_from_string(std::string(payload.str()));
                d_queue->handle(msg);
            }
        }

        // Tell runtime system how many output items we produced.
        return noutput_items;
    }

  } /* namespace scanner */
} /* namespace gr */

