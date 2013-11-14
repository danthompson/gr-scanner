from gnuradio import gr, gru, digital
import scanner
#hier block encapsulating the Smartnet-II control channel decoder
#could probably be split into its own file
#this should eventually spit out PMTs with control commands
class smartnet_ctrl_rx (gr.hier_block2):
    def __init__(self, rate): #TODO pass in chanlist
        gr.hier_block2.__init__(self,
                                "smartnet_ctrl_rx",
                                gr.io_signature(1,1,gr.sizeof_gr_complex),
                                gr.io_signature(0,0,0))

        self.set_assign_callback(None)
        self._queue = gr.msg_queue()
        self._async_sender = gru.msgq_runner(self._queue, self.msg_handler)

        self._syms_per_sec = 3600.
        self._sps = rate / self._syms_per_sec

        self._demod = scanner.fsk_demod(self._sps, 0.1)
        self._sof = digital.correlate_access_code_tag_bb("10101100",
                                                          0,
                                                         "smartnet_preamble")
        self._deinterleave = scanner.deinterleave()
        self._crc = scanner.crc(self._queue)
        self.connect(self, self._demod, self._sof, self._deinterleave, self._crc)

    #TODO reimplement the chanlist
    def cmd_to_freq(self, chanlist, cmd):
        if chanlist is None:
            if cmd < 0x2d0:
                freq = float(cmd * 0.025 + 851.0125)*1.e6
            else:
                freq = None
        else:
            if chanlist.get(str(cmd), None) is not None:
                freq = float(chanlist[str(cmd)])
            else:
                freq = None
        return freq

    def set_assign_callback(self, func):
        self._assign_callback = func

    def msg_handler(self, msg):
        print msg.to_string()
        [addr, groupflag, cmd] = [int(i) for i in msg.to_string().split(',')]
        freq = self.cmd_to_freq(None, cmd)
        if self._assign_callback is not None and freq is not None:
            self._assign_callback(addr, groupflag, freq)


class edacs_ctrl_rx(gr.hier_block2):
    def __init__(self, rate): #TODO pass in chanlist
        gr.hier_block2.__init__(self,
                                "edacs_ctrl_rx",
                                gr.io_signature(1,1,gr.sizeof_gr_complex),
                                gr.io_signature(0,0,0))

        self.set_assign_callback(None)
        self._queue = gr.msg_queue()
        self._async_sender = gru.msgq_runner(self._queue, self.msg_handler)

        self._syms_per_sec = 9600.
        self._sps = rate / self._syms_per_sec

        self._demod = scanner.fsk_demod(self._sps, 0.575)
        self._invert = scanner.invert()
        self._sof = digital.correlate_access_code_tag_bb("010101010101010101010111000100100101010101010101",
                                                          0,
                                                         "edacs_preamble")
        self._rx = scanner.edacs_pkt_rx(self._queue)
        self.connect(self, self._demod, self._invert, self._sof, self._rx)

    #TODO reimplement the chanlist
    def cmd_to_freq(self, chanlist, cmd):
        return None

    def set_assign_callback(self, func):
        self._assign_callback = func

    def msg_handler(self, msg):
        msg = scanner.edacs_pkt(int(msg.to_string(),16))
        commands = { 0xA0: "Data assignment",
                     0xA1: "Data assignment",
                     0xEC: "Phone patch",
                     0xEE: "Voice assigment",
                     0xFC: "Idle",
                     0xFD: "System ID"
                   }
        if msg["cmd"] not in commands:
            cmdstring = "N/A"
        else:
            cmdstring = commands[msg["cmd"]]
#        print "EDACS: Cmd: %s LCN: %x" % (cmdstring, msg["lcn"])
        if msg["cmd"] in (0xA0, 0xA1, 0xEC, 0xEE):
            if msg["id"].get_type() == 1:
                print "Individual call to %x on LCN %i" % (msg["id"]["id"], msg["lcn"])
            else:
                print "Group call to agency %i, fleet %i, subfleet %i on LCN %i" % (msg["id"]["agency"],
                                                                                    msg["id"]["fleet"], 
                                                                                    msg["id"]["subfleet"],
                                                                                    msg["lcn"])
        elif msg["cmd"] == 0xFD:
            print "EDACS system id: %x" % msg["id"]
        else:
            print "EDACS %s" % cmdstring
