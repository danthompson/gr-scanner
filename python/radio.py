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

from gnuradio import gr, blocks, uhd, analog
from gnuradio.filter import pfb, optfir
from gnuradio.eng_option import eng_option
from gnuradio.gr.pubsub import pubsub
from gnuradio.analog.fm_emph import fm_deemph
from optparse import OptionParser, OptionGroup
from math import pi
import scanner

class fm_demod(gr.hier_block2):
    """
    This class is mostly identical to the fm_demod_cf included
    in Gnuradio, except that we use bandpass taps instead of lowpass taps
    in order to remove the subaudible tone woobling <250Hz. We also use a
    pfb_arb_resampler instead of the usual decimating filter to get
    arbitrary sample rate output. This way we don't have to immediately
    follow the fm_demod with a resampler to get to whatever audio rate.
    It also incorporates a noise squelch.
    """
    def __init__(self, rate, decim, gate=False):
        gr.hier_block2.__init__(self,
                                "fm_demod",
                                gr.io_signature(1,1,gr.sizeof_gr_complex),
                                gr.io_signature(1,1,gr.sizeof_float))
        tau=75.e-6
        deviation = 5.e3
        k=rate/(2*pi*deviation)
        self.rate = rate
        self.quad = analog.quadrature_demod_cf(k)
        self.squelch = scanner.standard_squelch_ff(gate=gate)
        self.deemph = fm_deemph(rate, tau)
        self.nfilts = 32
        audio_taps = optfir.band_pass(self.nfilts,
                                      self.rate*self.nfilts,
                                      250,
                                      300,
                                      3000,
                                      4000,
                                      0.2,
                                      40)
        self.resamp = pfb.arb_resampler_fff(1./decim, audio_taps)
        self.connect(self, self.quad, self.squelch, self.deemph, self.resamp, self)

class filterbank(gr.hier_block2):
    def __init__(self, rate, channel_spacing):
        numchans = int(rate/channel_spacing)
        gr.hier_block2.__init__(self,
                                "filterbank",
                                gr.io_signature(1,1,gr.sizeof_gr_complex),
                                gr.io_signature(numchans,numchans,gr.sizeof_gr_complex))
        self._channel_spacing = channel_spacing
        self._rate = rate
        self._bank = pfb.channelizer_ccf(numchans, atten=60)
        print "Filterbank using %i channels" % numchans
        print "Filterbank filter length per channel: %i" % len(self._bank.pfb.taps()[0])
        self._map = [0]*numchans
        self._bank.set_channel_map(self._map)
        self.connect(self, self._bank)
        for i in xrange(numchans):
            self.connect((self._bank,i), (self,i))

    def set_freq(self, chan, offset):
        assert(offset % self._channel_spacing < 1e-4)
        chan_num = int(offset / self._channel_spacing)
        if(chan_num < 0):
            chan_num += int(self._rate / self._channel_spacing)
        self._map[chan] = chan_num
        self._bank.set_channel_map(self._map)

class wavsink_path(gr.hier_block2):
    """
    Gated squelch FM demod and file sink.
    TODO: 
        Figure out how to set file, 
        handle close/open, 
        handle appending, 
        maybe don't use .wav at all but sql.
    """
    def __init__(self, rate, filename, squelch):
        gr.hier_block2.__init__(self,
                                "logging_receiver",
                                gr.io_signature(nchans, nchans, gr.sizeof_gr_complex),
                                gr.io_signature(0,0,0))
        self._rate = rate
        self._filename = filename
        self._squelch = squelch
        self._audiorate = 8000
        self._decim = float(self._rate) / self._audiorate
        self._demod = fm_demod(self._rate, #rate
                               self._decim, #audio decimation
                               True) #gate samples when closed?
        self._valve = blks2.valve(gr.sizeof_float, False)
        self._audiosink = blocks.wavfile_sink(self._filename, 1, self._audiorate, 8)
        self.connect(self, self._demod, self._valve, self._audiosink)

    def enable(self, enable):
        """
        open the valve and allow recording to the wavfile (assuming signal for squelch to open)
        note: blks2.valve curiously calls an "open" squelch one that is blocked: like a switch instead
        of a valve. so we invert.
        """
        self._valve.set_open(not enable)
    def mute(self):
        self.enable(False)
    def unmute(self):
        self.enable(True)
    def squelch_open(self):
        return self._squelch.unmuted()

#TODO assign subscribers
class trunked_feed(gr.hier_block2, pubsub):
    def __init__(self, options, nchans=16):
        gr.hier_block2.__init__(self,
                                "trunked_feed",
                                gr.io_signature(0,0,gr.sizeof_gr_complex),
                                gr.io_signature(nchans,nchans,gr.sizeof_gr_complex))
        pubsub.__init__(self)
        self._options = options
        self._freqs = {"center": options.center_freq,
                       "ctrl": options.ctrl_freq,
                       "audio": options.ctrl_freq
                      }
        self._nchans = nchans

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
                src = blocks.file_source(gr.sizeof_gr_complex, options.source, repeat=False)
                print "Using file source %s" % options.source

        channel_spacing = 25e3
        self._channel_decimation = int(options.rate / channel_spacing)
        self._filter_bank = filterbank(rate=options.rate,
                                        channel_spacing=channel_spacing) #TODO parameterize

        self.connect(src, self._filter_bank)
        for i in xrange(self._nchans):
            self.connect((self._filter_bank,i), (self, i))

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
        if self.live_source():
            self._data_src.set_center_freq(freq)
            self._freqs["center"] = self._data_src.get_center_freq()

        self.set_freq("ctrl", self._freqs["ctrl"])
        self.set_freq("audio", self._freqs["audio"])

    def set_freq(self, chan, freq):
        print "Setting %s to %.4fMHz" % (chan, freq/1.e6)
        chan_num = ["ctrl", "audio"].index(chan)
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

