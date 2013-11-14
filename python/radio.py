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
from gnuradio.filter import pfb
from gnuradio.eng_option import eng_option
from gnuradio.gr.pubsub import pubsub
from optparse import OptionParser, OptionGroup
import threading
import time
import sys
import re
import scanner

class filterbank(gr.hier_block2):
    def __init__(self, rate, channel_spacing):
        numchans = int(rate/channel_spacing)
        gr.hier_block2.__init__(self,
                                "filterbank",
                                gr.io_signature(1,1,gr.sizeof_gr_complex),
                                gr.io_signature(numchans,numchans,gr.sizeof_gr_complex))
        self._channel_spacing = channel_spacing
        self._rate = rate
        self._bank = pfb.channelizer_ccf(numchans)
        self._map = [0]*numchans
        self._bank.set_channel_map(self._map)
        self.connect(self, self._bank)
        for i in xrange(numchans):
            self.connect(self._bank, (self,i))

    def set_freq(self, chan, offset):
        assert(offset % self._channel_spacing < 1e-4)
        chan_num = int(offset / self._channel_spacing)
        if(chan_num < 0):
            chan_num = int(self._rate / self._channel_spacing) + chan_num
        self._map[chan] = chan_num
        self._bank.set_channel_map(self._map)

class trunked_feed(gr.hier_block2, pubsub):
    def __init__(self, options):
        gr.hier_block2.__init__(self,
                                "trunked_feed",
                                gr.io_signature(0,0,gr.sizeof_gr_complex),
                                gr.io_signature(2,2,gr.sizeof_gr_complex))
        pubsub.__init__(self)
        self._options = options
        self._freqs = {"center": options.center_freq,
                       "ctrl": options.ctrl_freq,
                       "audio": options.ctrl_freq
                      }

        if options.source == "uhd":
            #UHD source by default
            from gnuradio import uhd
            src = uhd.usrp_source(options.args, uhd.io_type_t.COMPLEX_FLOAT32, 1)
            if options.subdev is not None:
                src.set_subdev_spec(options.subdev)
            if options.antenna is not None:
                src.set_antenna(options.antenna)

            #pick a reasonable sample rate
            master_clock_rate = src.get_clock_rate()
            acceptable_rates = [i.start() for i in src.get_samp_rates() if i.start() > 8e6 and (master_clock_rate / i.start()) % 4 == 0]
            src.set_samp_rate(min(acceptable_rates))
            self._channel_decimation = 1
            print "Using sample rate: %i" % min(acceptable_rates)
            if options.gain is None: #set to halfway
                g = src.get_gain_range()
                options.gain = (g.start()+g.stop()) / 2.0
            src.set_gain(options.gain)
            print "Gain is %i" % src.get_gain()

        #TODO: detect if you're using an RTLSDR or Jawbreaker
        #and set up accordingly.
        elif options.source == "hackrf" or options.source == "rtlsdr": #RTLSDR dongle or HackRF Jawbreaker
            import osmosdr
            src = osmosdr.source(options.source)
            wat = src.get_sample_rates()
            rates = range(int(wat.start()), int(wat.stop()+1), int(wat.step()))
            acceptable_rates = [i for i in rates if i >= 8e6]
            if len(acceptable_rates) < 1: #we're in single-channel-only mode
                acceptable_rates = (max(rates))
            src.set_sample_rate(min(acceptable_rates))
            src.get_samp_rate = src.get_sample_rate #alias for UHD compatibility in get_rate

            if options.gain is None:
                options.gain = 34
            src.set_gain(options.gain)
            print "Gain is %i" % src.get_gain()

        else:
            #semantically detect whether it's ip.ip.ip.ip:port or filename
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

        channel_spacing = 25e3
        self._channel_decimation = int(options.rate / channel_spacing)
        self._filter_bank = filterbank(rate=options.rate,
                                        channel_spacing=channel_spacing) #TODO parameterize
        self.connect(src, self._filter_bank)
        self.connect((self._filter_bank,0), (self,0))
        self.connect((self._filter_bank,1), (self,1))


        self._data_src = src
        self._source_name = options.source
        self.set_center_freq(options.center_freq)
        self.set_ctrl_freq(options.ctrl_freq)
        self.set_audio_freq(options.ctrl_freq) #wooboobooboboobobbo

        print "Using master rate: %f" % self.get_rate("master")
        print "Using ctrl rate: %f" % self.get_rate("ctrl")
        print "Using audio rate: %f" % self.get_rate("audio")

    def live_source(self):
        return self._options.source in ("uhd", "osmocom", "hackrf", "rtlsdr")

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

    def get_rate(self, channel="master"):
        if self.live_source():
            master_rate = self._data_src.get_samp_rate()
        else:
            master_rate = self._rate
        if channel == "master":
            return float(master_rate)
        else:
            return float(master_rate) / self._channel_decimation

    def set_center_freq(self, freq):
        if self._source_name == "uhd":
            tr = uhd.tune_request_t()
            tr.rf_freq_policy = uhd.tune_request_t.POLICY_MANUAL
            tr.dsp_freq_policy = uhd.tune_request_t.POLICY_MANUAL
            tr.rf_freq = freq
            tr.target_freq = freq
            tune_result = self._data_src.set_center_freq(tr,0)
            self._freqs["center"] = tune_result.actual_rf_freq
        elif self._source_name in ("hackrf", "rtlsdr"):
            self._data_src.set_center_freq(freq)
            self._freqs["center"] = self._data_src.get_center_freq()

        self.set_freq("ctrl", self._freqs["ctrl"])
        self.set_freq("audio", self._freqs["audio"])

    def set_freq(self, chan, freq):
        print "Setting %s to %.4fMHz" % (chan, freq/1.e6)
        chan_num = ["ctrl", "audio"].index(chan)
        if self._source_name == "uhd":
            tr = uhd.tune_request_t()
            tr.rf_freq_policy = uhd.tune_request_t.POLICY_MANUAL
            tr.dsp_freq_policy = uhd.tune_request_t.POLICY_MANUAL
            tr.dsp_freq = self._freqs["center"] - freq
            tr.rf_freq = self._freqs["center"]
            tr.target_freq = self._freqs["center"]
            tune_result = self._data_src.set_center_freq(tr, chan_num)
            print "Center frequency: %.4fMHz" % (tune_result.actual_rf_freq/1.e6)
            print "DSP frequency: %.4fMHz" % (tune_result.actual_dsp_freq/1.e6)
            print "%s channel: %.4fMHz" % (chan,
                                        ((tune_result.actual_rf_freq - tune_result.actual_dsp_freq)/1.e6)
                                        )
        else:
            #find the channel number
            offset = freq - self._freqs["center"]
            if abs(offset) > (self.get_rate("master") / 2):
                #TODO: handle this by retuning the center/operating single-channel
                print "Asked for a channel outside the band"
                return
            self._filter_bank.set_freq(chan_num, offset)
            print "Setting channel %i" % (chan_num)

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
                        help="Choose source: uhd, hackrf, rtlsdr, <filename>, or <ip:port> [default=%default]")
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
        group.add_option("-f", "--ctrl-freq", type="eng_float",
                         default=851.425e6,
                         help="control channel frequency [default=%default]")
        group.add_option("-c", "--center-freq", type="eng_float",
                         default=852e6,
                         help="tuner center frequency [default=%default]")
        group.add_option("-r", "--rate", type="eng_float", default=None,
                         help="sample rate, leave blank for automatic")
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

#instantiates a sample feed, control decoder, audio sink, and control
class scanner_radio (gr.top_block, pubsub):
    def __init__(self, options):
        gr.top_block.__init__(self)
        pubsub.__init__(self)
        self._options = options

        self._feed = trunked_feed(options)
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
        self._audio_path = audio_path(options)
        self.connect((self._feed,1), self._audio_path)

        #setup a callback to retune the audio feed freq
        self._data_path.set_assign_callback(self.handle_assignment)

    def handle_assignment(self, addr, groupflag, freq):
        #TODO handle all channel assignment and priority monitor stuff here
        if (addr & 0xFFF0) in self._monitor:# and self._tg_assignments.get(addr) != freq: #mask because last 4 bits is priority mask
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
        group.add_option("-t","--type", type="string", default="smartnet",
                         help="Network type (edacs or smartnet only) [default=%default]")
        parser.add_option_group(group)


