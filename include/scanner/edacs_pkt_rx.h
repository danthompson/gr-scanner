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


#ifndef INCLUDED_SCANNER_EDACS_PKT_RX_H
#define INCLUDED_SCANNER_EDACS_PKT_RX_H

#include <scanner/api.h>
#include <gnuradio/sync_block.h>

namespace gr {
  namespace scanner {

    /*!
     * \brief <+description of block+>
     * \ingroup scanner
     *
     */
    class SCANNER_API edacs_pkt_rx : virtual public gr::sync_block
    {
     public:
      typedef boost::shared_ptr<edacs_pkt_rx> sptr;

      /*!
       * \brief Return a shared_ptr to a new instance of scanner::edacs_pkt_rx.
       *
       * To avoid accidental use of raw pointers, scanner::edacs_pkt_rx's
       * constructor is in a private implementation
       * class. scanner::edacs_pkt_rx::make is the public interface for
       * creating new instances.
       */
      static sptr make(gr::msg_queue::sptr queue);
    };

  } // namespace scanner
} // namespace gr

#endif /* INCLUDED_SCANNER_EDACS_PKT_RX_H */

