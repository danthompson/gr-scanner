from gnuradio import gr
from gnuradio.gr.pubsub import pubsub
import scanner
from optparse import OptionParser, OptionGroup
#instantiates a sample feed, control decoder, audio sink, and control
class trunked_scanner(gr.top_block, pubsub):
    def __init__(self, options):
        gr.top_block.__init__(self)
        pubsub.__init__(self)
        self._options = options

        self._feed = scanner.trunked_feed(options, nchans=2)
        self._monitor = [int(i) for i in options.monitor.split(",")]
        self._tg_assignments = {}

        if options.type == 'smartnet':
            self._data_path = scanner.smartnet_ctrl_rx(self._feed.get_rate("ctrl"))
        elif options.type == 'edacs':
            self._data_path = scanner.edacs_ctrl_rx(self._feed.get_rate("ctrl"))
        else:
            raise Exception("Invalid network type (must be edacs or smartnet)")
        self.connect((self._feed,0), self._data_path)
        options.rate = self._feed.get_rate("audio")
        self._audio_path = scanner.audio_path(options)
        self.connect((self._feed,1), self._audio_path)

        #setup a callback to retune the audio feed freq
        self._data_path.set_assign_callback(self.handle_assignment)

    def handle_assignment(self, addr, groupflag, freq):
        #TODO handle all channel assignment and priority monitor stuff here
        if (addr & 0xFFF0) in self._monitor:# and self._tg_assignments.get(addr) != freq: #mask because last 4 bits is priority mask
            self._feed.set_audio_freq(freq)

        self._tg_assignments[addr] = freq

    def close(self):
        self._feed.close()

    @staticmethod
    def add_options(parser):
        scanner.trunked_feed.add_options(parser)
        scanner.audio_path.add_options(parser)
        group = OptionGroup(parser, "Scanner setup options")
        #Choose source
        group.add_option("-m","--monitor", type="string", default="0",
                        help="Monitor a list of talkgroups (comma-separated) [default=%default]")
        group.add_option("-t","--type", type="string", default="smartnet",
                         help="Network type (edacs or smartnet only) [default=%default]")
        parser.add_option_group(group)


