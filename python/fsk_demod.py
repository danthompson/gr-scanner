#!/usr/bin/env python
""" Block to demodulate FSK via coherent PLL frequency estimation
"""

from gnuradio import gr, gru, digital, analog, blocks, filter
from gnuradio import eng_notation
from math import pi

class fsk_demod(gr.hier_block2):
    def __init__(self, sps, gain_mu, offset):
        gr.hier_block2.__init__(self, "fsk_demod",
                                gr.io_signature(1, 1, gr.sizeof_gr_complex), # Input signature
                                gr.io_signature(1, 1, gr.sizeof_char)) # Output signature

        self._sps = float(sps)
        self._gain_mu = gain_mu # for the clock recovery block
        self._freqoffset = offset
        self._mu = 0.5
        self._omega_relative_limit = 0.3
        self._samples_per_second = self._sps*3600 #TODO MAGIC

        #first bring that input stream down to a manageable level
        self._clockrec_oversample = 3

        self._decim = int(self._sps / self._clockrec_oversample)
        self._downsampletaps = filter.firdes.low_pass(1.0/self._decim,
                                                self._samples_per_second, 10000,
                                                1000, filter.firdes.WIN_HANN)

        print "Demodulator decimation: %i" % self._decim
        print "Demodulator rate: %i" % (self._samples_per_second / self._decim)

        #save a bunch of CPU if we're operating at the center freq already
        if(self._freqoffset == 0):
            self._downsample = filter.fft_filter_ccc(self._decim,
                                                     self._downsampletaps)
        else:
            self._downsample = filter.freq_xlating_fir_filter_ccf(self._decim, #decimation
                                                                  self._downsampletaps, #taps
                                                                  self._freqoffset, #freq offset
                                                                  self._samples_per_second) #sampling rate

        #using a pll to demod gets you a nice IIR LPF response for free
        self._demod = analog.pll_freqdet_cf(2.0 / self._clockrec_oversample, #gain alpha, rad/samp
                                         2*pi/self._clockrec_oversample,  #max freq, rad/samp
                                        -2*pi/self._clockrec_oversample)  #min freq, rad/samp

        self._clockrec_sps = self._sps / self._decim

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

        self.connect(self, self._downsample, self._carriertrack, self._demod, self._softbits, self._slicer, self)
