from gnuradio import gr, filter, analog, audio
from optparse import OptionParser, OptionGroup

#audio path to speaker
class audio_path (gr.hier_block2):
    def __init__(self, options):
        gr.hier_block2.__init__(self,
                                "audio_path",
                                gr.io_signature(1,1,gr.sizeof_gr_complex),
                                gr.io_signature(0,0,gr.sizeof_gr_complex))
        self._options = options
        self.audiorate = options.audio_rate
        self.prefilter_decim = float(options.rate) / self.audiorate
        print "Audio demod decimation: %f" % self.prefilter_decim
        self.audio_prefilter = filter.pfb.arb_resampler_ccf(1.0/self.prefilter_decim)

        #on a trunked network where you know you will have good signal,
        #a carrier power squelch works well. real FM receivers use a
        #noise squelch, where the received audio is high-passed above
        #the cutoff and then fed to a reverse squelch. If the power is
        #then BELOW a threshold, open the squelch.
        self.squelch = analog.pwr_squelch_cc(options.squelch, #squelch point
                                            alpha = 0.1, #wat
                                            ramp = 10, #wat
                                            gate = False)

        self.audiodemod = analog.fm_demod_cf(self.audiorate, #rate
                            1, #audio decimation
                            4000, #deviation
                            3000, #audio passband
                            4000, #audio stopband
                            options.volume, #gain
                            75e-6) #deemphasis constant

        #the filtering removes FSK data woobling from the subaudible channel
        self.audiofilttaps = filter.firdes.high_pass(1, self.audiorate, 300,
                                                        50, filter.firdes.WIN_HANN)
        self.audiofilt = filter.fft_filter_fff(1, self.audiofilttaps)
        self.audiosink = audio.sink(int(self.audiorate), "")

        self.connect(self, self.audio_prefilter, self.squelch, self.audiodemod, self.audiofilt, self.audiosink)

    @staticmethod
    def add_options(parser):
        group = OptionGroup(parser, "Audio setup options")
        group.add_option("-v", "--volume", type="eng_float", default=2.5,
                            help="set volume gain for audio output [default=%default]")
        group.add_option("-s", "--squelch", type="eng_float", default=-40,
                            help="set audio squelch level in dBfs(default=%defaultdB, play with it)")
        group.add_option("-a", "--audio-rate", type="eng_float", default=48e3,
                            help="set audio rate [default=%default]")
        parser.add_option_group(group)

