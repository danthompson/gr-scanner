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
#include <gnuradio/tags.h>
#include "deinterleave_impl.h"

#define VERBOSE 0

namespace gr {
  namespace scanner {

    deinterleave::sptr
    deinterleave::make()
    {
      return gnuradio::get_initial_sptr
        (new deinterleave_impl());
    }

    /*
     * The private constructor
     */
    deinterleave_impl::deinterleave_impl()
      : gr::block("deinterleave",
              gr::io_signature::make(1, 1, sizeof(char)),
              gr::io_signature::make(1, 1, sizeof(char)))
    {
        set_relative_rate((double)(76.0/84.0));
        set_output_multiple(76*2);
    }

    /*
     * Our virtual destructor.
     */
    deinterleave_impl::~deinterleave_impl()
    {
    }

    void
    deinterleave_impl::forecast (int noutput_items, gr_vector_int &ninput_items_required)
    {
        /* <+forecast+> e.g. ninput_items_required[0] = noutput_items */
        int size = (noutput_items * 84) / 76;
        ninput_items_required[0] = size;
    }

    int
    deinterleave_impl::general_work (int noutput_items,
                       gr_vector_int &ninput_items,
                       gr_vector_const_void_star &input_items,
                       gr_vector_void_star &output_items)
    {
        const char *in = (const char *) input_items[0];
        char *out = (char *) output_items[0];

        int size = ninput_items[0] - 84;
        if(size <= 0) {
            consume_each(0);
            return 0; //better luck next time
        }

        uint64_t abs_sample_cnt = nitems_read(0);
        std::vector<gr::tag_t> preamble_tags;

        uint64_t outlen = 0; //output sample count

        get_tags_in_range(preamble_tags, 0, abs_sample_cnt, abs_sample_cnt + size, pmt::string_to_symbol("smartnet_preamble"));
        if(preamble_tags.size() == 0) {
            consume_each(size);
            return 0;
        }

        std::vector<gr::tag_t>::iterator tag_iter;
        for(tag_iter = preamble_tags.begin(); tag_iter != preamble_tags.end(); tag_iter++) {
            uint64_t mark = tag_iter->offset - abs_sample_cnt;

            if(VERBOSE) std::cout << "found a preamble at " << tag_iter->offset << std::endl;

            for(int k=0; k<76/4; k++) {
                for(int l=0; l<4; l++) {
                out[k*4 + l] = in[mark + k + l*19];
                }
            }

            //since you're a nonsynchronized block, you have to reissue a
            //tag with the correct output sample number
            add_item_tag(0, //stream ID
                    nitems_written(0) + outlen, //sample
                    pmt::string_to_symbol("smartnet_frame"), //key
                    pmt::pmt_t() //data (unused here)
                    );
            outlen += 76;
        }

        consume_each(preamble_tags.back().offset - abs_sample_cnt + 84);
        if(VERBOSE) std::cout << "consumed " << (preamble_tags.back().offset - abs_sample_cnt + 84) << ", produced " << outlen << std::endl;
        return outlen;
    }

  } /* namespace scanner */
} /* namespace gr */

