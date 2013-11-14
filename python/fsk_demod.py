#!/usr/bin/env python
""" Block to demodulate FSK via coherent PLL frequency estimation
"""

from gnuradio import gr, gru, digital, analog, blocks, filter
from gnuradio import eng_notation
from gnuradio.filter import pfb
from math import pi

class fsk_demod(gr.hier_block2):
    def __init__(self, sps, gain_mu):
        gr.hier_block2.__init__(self, "fsk_demod",
                                gr.io_signature(1, 1, gr.sizeof_gr_complex), # Input signature
                                gr.io_signature(1, 1, gr.sizeof_char)) # Output signature

        self._sps = float(sps)
        self._gain_mu = gain_mu # for the clock recovery block
        self._mu = 0.5
        self._omega_relative_limit = 0.35

        #first bring that input stream down to a manageable level
        self._clockrec_oversample = 3.0
        self._decim = self._sps / self._clockrec_oversample
        print "Demodulator decimation: %f" % self._decim
        self._downsampletaps = filter.firdes.low_pass(1.0/self._decim,
                                                1.0, 0.4,
                                                0.05, filter.firdes.WIN_HANN)

#        self._downsample = filter.fft_filter_ccc(self._decim,
#                                                self._downsampletaps)

        #sure this works but it's a little heavy on the CPU at high rates
        self._downsample = pfb.arb_resampler_ccf(1/self._decim)

        self._clockrec_sps = self._sps / self._decim

        #using a pll to demod gets you a nice IIR LPF response for free
        self._demod = analog.pll_freqdet_cf(2.0 / self._clockrec_sps, #gain alpha, rad/samp
                                         2*pi/self._clockrec_sps,  #max freq, rad/samp
                                        -2*pi/self._clockrec_sps)  #min freq, rad/samp

        #band edge filter FLL with a low bandwidth is very good
        #at synchronizing to continuous FSK signals
        self._carriertrack = digital.fll_band_edge_cc(self._clockrec_sps,
                                                      0.6, #rolloff factor
                                                      64,  #taps
                                                      1.0) #loop bandwidth

        print "Samples per symbol: %f" % (self._clockrec_sps,)
        self._softbits = digital.clock_recovery_mm_ff(self._clockrec_sps,
                                                 0.25*self._gain_mu*self._gain_mu, #gain omega, = mu/2 * mu_gain^2
                                                 self._mu, #mu (decision threshold)
                                                 self._gain_mu, #mu gain
                                                 self._omega_relative_limit) #omega relative limit

        self._slicer = digital.binary_slicer_fb()

        if self._decim > 1:
            self.connect(self, self._downsample, self._carriertrack, self._demod, self._softbits, self._slicer, self)
        else:
            self.connect(self, self._carriertrack, self._demod, self._softbits, self._slicer, self)
