#
# Copyright 2005,2007,2012 Free Software Foundation, Inc.
#
# This file is part of GNU Radio
#
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# GNU Radio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#

import math
from gnuradio import gr, analog, blocks
from gnuradio.filter import iir_filter_ffd, single_pole_iir_filter_ff

class standard_squelch_ff(gr.hier_block2):
    """
    This block implements what's sometimes called a noise squelch. It opens
    when it detects FM quieting due to the capture effect. By passing the
    received audio through a pair of complementary high- and low-pass filters
    and comparing their envelope power, the squelch is opened or closed. This
    block is only suitable for use on demodulated FM analog audio channels.

    Do not bandlimit the audio before this block; doing so will prevent the
    squelch from closing at the correct threshold.

    When using an audio sink you'll want to keep gate=False to prevent audio
    underruns.

    Args:
        alpha: averaging constant of the squelch (float)
        threshold_db: ratio of SNR at which to open the squelch (float dB)
        gate: whether to gate (block) the output or issue zeroes when closed (bool)
    """
    def __init__(self, alpha=0.0001, threshold_db=-10, gate=False):
        gr.hier_block2.__init__(self, "standard_squelch",
                                gr.io_signature(1, 1, gr.sizeof_float), # Input signature
                                gr.io_signature(1, 1, gr.sizeof_float)) # Output signature


        #fixed coeffs, Chebyshev type 2 LPF=[0, 0.4, 0.7], HPF=[0.4, 0.7, 1]
        self.low_iir = iir_filter_ffd([0.12260106307699403, -0.22058023529806434, 0.22058023529806436, -0.12260106307699434],
                                             [1.00000000000000000, 0.7589332900264623, 0.5162740252200005, 0.07097813844342238],
                                             False)
        self.low_square = blocks.multiply_ff()
        self.low_smooth = single_pole_iir_filter_ff(alpha)

        self.hi_iir = iir_filter_ffd([0.1913118666668073, 0.4406071020350289, 0.4406071020350288, 0.19131186666680736],
                                            [1.000000000000000000, -0.11503633296078866, 0.3769676347066441, 0.0019066356578167866], 
                                             False)
        self.hi_square = blocks.multiply_ff()
        self.hi_smooth = single_pole_iir_filter_ff(alpha)

        #inverted thresholds because we reversed the division block inputs
        #to make the threshold output 1 when open and 0 when closed
        self.gate = blocks.threshold_ff(0,0,0)
        self.set_threshold(threshold_db)
        self.squelch_lpf = single_pole_iir_filter_ff(alpha)
        self.squelch_mult = blocks.multiply_ff()
        self.div = blocks.divide_ff()

        #This is horrible, but there's no better way to gate samples.
        #the block is fast, so realistically there's little overhead
        #TODO: implement a valve block that gates based on an input value
        self.valve = analog.pwr_squelch_ff(-100, 1, 0, gate)

        #sample path
        self.connect(self, (self.squelch_mult, 0))

        #filter path (LPF)
        self.connect(self,self.low_iir)
        self.connect(self.low_iir,(self.low_square,0))
        self.connect(self.low_iir,(self.low_square,1))
        self.connect(self.low_square,self.low_smooth,(self.div,0))

        #filter path (HPF)
        self.connect(self,self.hi_iir)
        self.connect(self.hi_iir,(self.hi_square,0))
        self.connect(self.hi_iir,(self.hi_square,1))
        self.connect(self.hi_square,self.hi_smooth,(self.div,1))

        #control path
        self.connect(self.div, self.gate, self.squelch_lpf, (self.squelch_mult,1))
        self.connect(self.squelch_mult, self)

    def set_threshold(self, threshold_db):
        self.gate.set_hi(1/(10**(threshold_db/10.)))
        self.gate.set_lo(1/(10**((threshold_db+1)/10.)))

    def threshold(self):
        return self.gate.hi()

    def set_alpha(self, alpha):
        self._alpha = alpha
        self.low_smooth.set_taps(alpha)
        self.hi_smooth.set_taps(alpha)
        self.squelch_lpf.set_taps(alpha)

    def alpha(self):
        return self._alpha

    def set_gate(self, gate):
        self.valve.set_gate(gate)

    def gate(self):
        return self.valve.gate()

    #TODO: this is historical, not sure what it's for
    def squelch_range(self):
        return (0.0, 1.0, 1.0/100)
