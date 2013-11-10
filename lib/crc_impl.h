/* -*- c++ -*- */
/* 
 * Copyright 2013 Nick Foster
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

#ifndef INCLUDED_SCANNER_CRC_IMPL_H
#define INCLUDED_SCANNER_CRC_IMPL_H

#include <gnuradio/tags.h>
#include <scanner/crc.h>

namespace gr {
  namespace scanner {
    struct smartnet_packet {
        bool groupflag;
        unsigned int command;
        unsigned int address;
        unsigned int crc;
    };

    class crc_impl : public crc
    {
     private:
        void smartnet_ecc(char *out, const char *in);
        bool crc(const char *in);
        smartnet_packet parse(const char *in);

        gr::msg_queue::sptr d_queue;

     public:
      crc_impl(gr::msg_queue::sptr queue);
      ~crc_impl();

      // Where all the action really happens
      int work(int noutput_items,
            gr_vector_const_void_star &input_items,
            gr_vector_void_star &output_items);
    };

  } // namespace scanner
} // namespace gr

#endif /* INCLUDED_SCANNER_CRC_IMPL_H */

