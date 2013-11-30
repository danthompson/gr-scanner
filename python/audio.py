from gnuradio import gr, filter, analog, audio
from optparse import OptionParser, OptionGroup
import scanner

#audio path to speaker
class audio_path (gr.hier_block2):
    def __init__(self, options):
        gr.hier_block2.__init__(self,
                                "audio_path",
                                gr.io_signature(1,1,gr.sizeof_gr_complex),
                                gr.io_signature(0,0,0))
        self._options = options
        self.audiorate = options.audio_rate
        self.decim = float(options.rate) / self.audiorate
        print "Audio demod decimation: %f" % self.decim
        self.demod = scanner.fm_demod(options.rate, self.decim, False)
        self.volume = blocks.multiply_const_ff(options.volume)
        self.audiosink = audio.sink(int(self.audiorate), "")
        self.connect(self, self.demod, self.volume, self.audiosink)

    def set_volume(self, volume):
        self.volume.set_k(volume)

    @staticmethod
    def add_options(parser):
        group = OptionGroup(parser, "Audio setup options")
        group.add_option("-v", "--volume", type="eng_float", default=2.5,
                            help="set volume gain for audio output [default=%default]")
        group.add_option("-s", "--squelch", type="eng_float", default=-10,
                            help="set audio squelch level (default=%defaultdB, play with it)")
        group.add_option("-a", "--audio-rate", type="eng_float", default=48e3,
                            help="set audio rate [default=%default]")
        parser.add_option_group(group)

