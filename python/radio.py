# Copyright 2013 Nick Foster
# 
# This file is part of gr-scanner
# 
# gr-scanner is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# gr-scanner is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with gr-scanner; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#

# Radio interface for gr-scanner
# Handles all hardware- and source-related functionality
# You pass it options, it gives you data.
# It uses the pubsub interface to allow clients to subscribe to its data feeds.

from gnuradio import gr, gru, eng_notation, filter, blocks, digital, analog, audio, uhd
from gnuradio.filter import optfir
from gnuradio.eng_option import eng_option
from gnuradio.gr.pubsub import pubsub
from optparse import OptionParser, OptionGroup
import threading
import time
import sys
import re
import scanner

#hier block encapsulating the Smartnet-II control channel decoder
#could probably be split into its own file
#this should eventually spit out PMTs with control commands
class smartnet_ctrl_rx (gr.hier_block2):
    def __init__(self, rate, offset): #TODO pass in chanlist
        gr.hier_block2.__init__(self,
                                "smartnet_ctrl_rx",
                                gr.io_signature(1,1,gr.sizeof_gr_complex),
                                gr.io_signature(0,0,0))

        self.set_assign_callback(None)
        self._queue = gr.msg_queue()
        self._async_sender = gru.msgq_runner(self._queue, self.msg_handler)

        self._syms_per_sec = 3600.
        self._sps = rate / self._syms_per_sec

        self._demod = scanner.fsk_demod(self._sps, 0.1, offset)
        self._sof = digital.correlate_access_code_tag_bb("10101100",
                                                          0,
                                                         "smartnet_preamble")
        self._deinterleave = scanner.deinterleave()
        self._crc = scanner.crc(self._queue)
#        self._debug = blocks.file_sink(gr.sizeof_gr_complex, "debug.dat")

        self.connect(self, self._demod, self._sof, self._deinterleave, self._crc)
#        self.connect(self, self._debug)
    #TODO add in setters/getters for rate
    #TODO fix the kludge in fsk_demod (3600bps fixed)

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

#trunked_feed does whatever it takes to provide a control channel feed on ch1
#and an audio channel feed on ch2.
#Right now this is USRP-only, and single-channel-audio only.
#Question: Should this class be able to output a very-wide aggregate channel,
#multiple audio channels at will (not possible w/o GRAS?), or only single channel?
#There's a lot of junk in here that will have to be replicated if you use another
#class to handle the aggregate case.
class trunked_feed(gr.hier_block2, pubsub):
    def __init__(self, options):
        gr.hier_block2.__init__(self,
                                "scanner_trunked_feed",
                                gr.io_signature(0,0,gr.sizeof_gr_complex),
                                gr.io_signature(2,2,gr.sizeof_gr_complex))
        pubsub.__init__(self)
        self._options = options
        self._freqs = {"center": options.center_freq,
                       "ctrl": options.ctrl_freq,
                       "audio": options.ctrl_freq
                      }
        #create a source.
        if options.source == "uhd":
            #UHD source by default
            from gnuradio import uhd
            #create two channels; this lets us tune one to ctrl chan and the other to audio
            src = uhd.usrp_source(options.args, uhd.io_type_t.COMPLEX_FLOAT32, 2)
            if options.subdev is not None:
                src.set_subdev_spec(options.subdev) #both use same frontend
            else:
                src.set_subdev_spec("A:0 A:0")
            if options.antenna is not None:
                src.set_antenna(options.antenna)
            src.set_samp_rate(options.rate)
            if options.gain is None: #set to halfway
                g = src.get_gain_range()
                options.gain = (g.start()+g.stop()) / 2.0
            src.set_gain(options.gain)
            print "Gain is %i" % src.get_gain()

        #TODO: detect if you're using an RTLSDR or Jawbreaker
        #and set up accordingly.
        elif options.source == "osmocom": #RTLSDR dongle or HackRF Jawbreaker
            raise Exception("Error: this isn't implemented yet.")
            import osmosdr
            src = osmosdr.source(options.args)
            src.set_sample_rate(options.rate)
            src.get_samp_rate = src.get_sample_rate #alias for UHD compatibility
            if not src.set_center_freq(162.0e6 * (1 + options.error/1.e6)):
                print "Failed to set initial frequency"
            else:
                print "Tuned to %.3fMHz" % (src.get_center_freq() / 1.e6)

            if options.gain is None:
                options.gain = 34
            src.set_gain(options.gain)
            print "Gain is %i" % src.get_gain()

        else:
            #semantically detect whether it's ip.ip.ip.ip:port or filename
            raise Exception("Error: this isn't implemented yet.")
            self._rate = options.rate
            if ':' in options.source:
                try:
                    ip, port = re.search("(.*)\:(\d{1,5})", options.source).groups()
                except:
                    raise Exception("Please input UDP source e.g. 192.168.10.1:12345")
                src = blocks.udp_source(gr.sizeof_gr_complex, ip, int(port))
                print "Using UDP source %s:%s" % (ip, port)
            else:
                src = blocks.file_source(gr.sizeof_gr_complex, options.source)
                print "Using file source %s" % options.source

        self.connect((src,0), (self,0))
        self.connect((src,1), (self,1))
        self._data_src = src
        self.set_center_freq(options.center_freq)
        self.set_freq("ctrl", options.ctrl_freq)
        self.set_freq("audio", options.ctrl_freq) #wooboobooboboobobbo

    def live_source(self):
        return self._options.source=="uhd" or self._options.source=="osmocom"

    def set_gain(self, gain):
        if self.live_source():
            self._u.set_gain(gain)
            print "Gain is %f" % self.get_gain()
        return self.get_gain()

    def set_rate(self, rate):
        self._rx_path.set_rate(rate)
        return self._data_src.set_rate(rate) if self.live_source() else self._rate

    def get_gain(self):
        return self._data_src.get_gain() if self.live_source() else 0

    def get_rate(self):
        return self._data_src.get_samp_rate() if self.live_source() else self._rate

    def set_center_freq(self, freq):
        tr = uhd.tune_request_t()
        tr.rf_freq_policy = uhd.tune_request_t.POLICY_MANUAL
        tr.dsp_freq_policy = uhd.tune_request_t.POLICY_MANUAL
        tr.rf_freq = freq
        tr.target_freq = freq
        tune_result = self._data_src.set_center_freq(tr,0)
        self._freqs["center"] = freq
        self.set_freq("ctrl", self._freqs["ctrl"])
        self.set_freq("audio", self._freqs["audio"])

    def set_freq(self, chan, freq):
        print "Setting %s to %.3fMHz" % (chan, freq/1.e6)
        chan_num = ["ctrl", "audio"].index(chan)
        tr = uhd.tune_request_t()
        tr.rf_freq_policy = uhd.tune_request_t.POLICY_MANUAL
        tr.dsp_freq_policy = uhd.tune_request_t.POLICY_MANUAL
        tr.dsp_freq = self._freqs["center"] - freq
        tr.rf_freq = self._freqs["center"]
        tr.target_freq = self._freqs["center"]
        tune_result = self._data_src.set_center_freq(tr, chan_num)
        print "Center frequency: %.3fMHz" % (tune_result.actual_rf_freq/1.e6)
        print "DSP frequency: %.3fMHz" % (tune_result.actual_dsp_freq/1.e6)
        print "%s channel: %.3fMHz" % (chan,
                                    ((tune_result.actual_rf_freq - tune_result.actual_dsp_freq)/1.e6)
                                    )
        self._freqs[chan] = freq

    def set_ctrl_freq(self, freq):
        self.set_freq("ctrl", freq)

    def set_audio_freq(self, freq):
        self.set_freq("audio", freq)

    def close(self):
        self._data_src = None

    @staticmethod
    def add_options(parser):
        group = OptionGroup(parser, "Radio setup options")

        #Choose source
        group.add_option("-s","--source", type="string", default="uhd",
                        help="Choose source: uhd, osmocom, <filename>, or <ip:port> [default=%default]")
        #UHD/Osmocom args
        group.add_option("-R", "--subdev", type="string",
                        help="select USRP Rx side A or B", metavar="SUBDEV")
        group.add_option("-A", "--antenna", type="string",
                        help="select which antenna to use on daughterboard")
        group.add_option("-D", "--args", type="string",
                        help="arguments to pass to radio constructor", default="")
        group.add_option("-g", "--gain", type="int", default=None,
                        help="set RF gain", metavar="dB")
        parser.add_option("-e", "--error", type="eng_float", default=0,
                            help="set offset error of device in ppm [default=%default]")
        #RX path args
        group.add_option("-r", "--rate", type="eng_float", default=250e3,
                        help="set sample rate [default=%default]")
        group.add_option("-f", "--ctrl-freq", type="eng_float",
                         default=851.425e6,
                         help="control channel frequency [default=%default]")
        group.add_option("-c", "--center-freq", type="eng_float",
                         default=852e6,
                         help="tuner center frequency [default=%default]")
        parser.add_option_group(group)

class audio_path (gr.hier_block2, pubsub):
    def __init__(self, options):
        gr.hier_block2.__init__(self,
                                "audio_path",
                                gr.io_signature(1,1,gr.sizeof_gr_complex),
                                gr.io_signature(0,0,gr.sizeof_gr_complex))
        pubsub.__init__(self)
        self._options = options
        self.audiorate = options.audio_rate
        self.audiotaps = filter.firdes.low_pass(1, options.rate, 8000, 2000,
                                                filter.firdes.WIN_HANN)
        print "Number of audio taps: %i" % len(self.audiotaps)
        self.prefilter_decim = int(options.rate / self.audiorate) #might have to use a rational resampler for audio
        print "Prefilter decimation: %i" % self.prefilter_decim
        self.audio_prefilter = filter.fft_filter_ccc(self.prefilter_decim, #decimation
                                        self.audiotaps) #taps

        #on a trunked network where you know you will have good signal,
        #a carrier power squelch works well. real FM receviers use a
        #noise squelch, where the received audio is high-passed above
        #the cutoff and then fed to a reverse squelch. If the power is
        #then BELOW a threshold, open the squelch.
        self.squelch = analog.pwr_squelch_cc(options.squelch, #squelch point
                                            alpha = 0.1, #wat
                                            ramp = 10, #wat
                                            gate = False)

        self.audiodemod = analog.fm_demod_cf(options.rate/self.prefilter_decim, #rate
                            1, #audio decimation
                            4000, #deviation
                            3000, #audio passband
                            4000, #audio stopband
                            1, #gain
                            75e-6) #deemphasis constant

        #the filtering removes FSK data woobling from the subaudible channel (might be able to combine w/lpf above)
        self.audiofilttaps = filter.firdes.high_pass(1, self.audiorate, 300,
                                                        50, filter.firdes.WIN_HANN)
        self.audiofilt = filter.fft_filter_fff(1, self.audiofilttaps)
        self.audiogain = blocks.multiply_const_ff(options.volume)
        self.audiosink = audio.sink(int(self.audiorate), "")

        self.connect(self, self.audio_prefilter, self.squelch, self.audiodemod, self.audiofilt, self.audiogain, self.audiosink)

    @staticmethod
    def add_options(parser):
        group = OptionGroup(parser, "Audio setup options")
        group.add_option("-v", "--volume", type="eng_float", default=0.2,
                            help="set volume gain for audio output [default=%default]")
        group.add_option("-s", "--squelch", type="eng_float", default=-40,
                            help="set audio squelch level in dBfs(default=%defaultdB, play with it)")
        group.add_option("-a", "--audio-rate", type="eng_float", default=48e3,
                            help="set audio rate [default=%default]")
        parser.add_option_group(group)

#instantiates a sample feed, control decoder, audio sink, and control
class scanner_radio (gr.top_block, pubsub):
    def __init__(self, options):
        gr.top_block.__init__(self)
        pubsub.__init__(self)
        self._options = options

        self._feed = trunked_feed(options)
        self._rate = self._feed.get_rate()
        self._monitor = [int(i) for i in options.monitor.split(",")]
        self._tg_assignments = {}
        print "Rate is %i" % (self._rate,)

        self._data_path = smartnet_ctrl_rx(self._rate, 0)
        self.connect((self._feed,0), self._data_path)
        self._audio_path = audio_path(options)
        self.connect((self._feed,1), self._audio_path)

        #setup a callback to retune the audio feed freq
        self._data_path.set_assign_callback(self.handle_assignment)

    def handle_assignment(self, addr, groupflag, freq):
        #TODO handle all channel assignment and priority monitor stuff here
        if (addr & 0xFFF0) in self._monitor \
        and self._tg_assignments.get(addr) != freq: #mask because last 4 bits is priority mask
            self._feed.set_audio_freq(freq)

        self._tg_assignments[addr] = freq

    @staticmethod
    def add_options(parser):
        trunked_feed.add_options(parser)
        audio_path.add_options(parser)
        group = OptionGroup(parser, "Scanner setup options")
        #Choose source
        group.add_option("-m","--monitor", type="string", default="0",
                        help="Monitor a list of talkgroups (comma-separated) [default=%default]")
        parser.add_option_group(group)


