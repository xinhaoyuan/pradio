import subprocess
import json
import mplayer
import time
import urwid
import pykka
import sys

class MplayerActor(pykka.ThreadingActor):

    def __init__(self, args):
        super(MplayerActor, self).__init__()
        self._debug = args.debug
        self._refresh_interval = args.refresh_interval
        self._last_refresh = time.time()
        self._cache_timepos = None
        self._cache_length = None
        self._cache_volume = None
        self._cache_percent = None
        if self._debug:
            self._player = mplayer.Player()
        else:
            self._player = mplayer.Player(stderr = open("/dev/null", "w"))

    def on_receive(self, msg):
        ret = None
        now = time.time()
        if now - self._last_refresh > self._refresh_interval:
            self._last_refresh = now
            self._cache_timepos = self._player.time_pos
            self._cache_length = self._player.length
            self._cache_volume = self._player.volume
            self._cache_percent = self._player.percent_pos
            pass

        if msg[0] == "play":
            self._cache_timepos = None
            self._cache_length = None
            self._cache_volume = None
            self._cache_percent = None
            self._player.loadfile(msg[1])
        elif msg[0] == "get_status":
            ret = (self._cache_timepos, self._cache_length, self._cache_volume, self._cache_percent)
        elif msg[0] == "toggle_mute":
            self._player.mute = not self._player.mute
        elif msg[0] == "adjust_volume":
            self._cache_volume = min(100, max(0, self._player.volume + msg[1]))
            self._player.volume = self._cache_volume
        else:
            pass

        return ret

class Player:

    def __init__(self, args):
        self._song_format = args.song_format
        self._refresh_interval = args.refresh_interval
        self._switch_threshold = args.switch_threshold
        self._proc = subprocess.Popen(args.args,
                                stdin = subprocess.PIPE,
                                stdout = subprocess.PIPE)
        self._debug = args.debug
        self._player_actor = MplayerActor.start(args)
        self._title_widget = urwid.Text("", align = "center")
        self._progress_widget = urwid.Text("", align = "center")
        self._volume_widget = urwid.Text("", align = "center")
        self._output_widget = urwid.Pile([])
        self.frame = urwid.Frame(
            header= urwid.Pile([
                self._title_widget,
                self._progress_widget,
                self._volume_widget,
                urwid.Divider("-"),
            ]),
            body = urwid.Filler(self._output_widget, valign = 'top'),
            focus_part = 'header')
        self._current_song_title = None
        self._last_stopped_time = None
        self._loop = None
        self._just_started = True
        pass

    def log(self, log):
        self._last_log = urwid.Text(log)
        self._output_widget.contents.insert(0, (self._last_log, ("pack", None)))
        self._loop.draw_screen()

    def start(self):
        self.log("Welcome to PRadio. Press [h] for the help on keys.")
        self.next_song()

    def rate(self, rating):
        self.log("Rating the current song as %d ..." % rating)
        try:
            self._proc.stdin.write(json.dumps({ "type" : "cmd_rate", "rating" : rating }).encode("utf-8"))
            self._proc.stdin.write(b"\n")
            self._proc.stdin.flush()
            resp = json.loads(self._proc.stdout.readline().decode("utf-8"))
            assert(resp["type"] == "reply_ok")
            self._last_log.set_text("Rated the current song as %d" % rating)
        except Exception as e:
            self._last_log.set_text("Got error rating the current song: %s" % str(e))
            pass
        pass

    def next_song(self):
        """
        Query for the next song, set up mplayer, and generate the title based on the returned data.
        """
        self._last_stopped_time = None
        self.log("Requesting the next song ...")
        try:
            self._proc.stdin.write(json.dumps({ "type" : "cmd_next" }).encode("utf-8"))
            self._proc.stdin.write(b"\n")
            self._proc.stdin.flush()
            resp = json.loads(self._proc.stdout.readline().decode("utf-8"))
            assert(resp["type"] == "reply_ok")
            
            data = resp["data"]
            url = data["url"]
            
            self._current_song_title = self._song_format.format(
                title = data["title"] if "title" in data else "?",
                album = data["album"] if "album" in data else "?",
                singers = "/".join(data["singers"]) if "singers" in data else "?")
                
            self._last_log.set_text("Playing: {}".format(self._current_song_title))
            if self._debug:
                if "raw_data" in resp:
                    self.log(json.dumps(resp["raw_data"]))
                self.log(json.dumps(data))
                self.log(url)

            self._player_actor.tell(["play", url])
            self.update()
        except Exception as e:
            self.log("Got error playing next song: %s" % str(e))
            pass
        pass

    def toggle_mute(self):
        self._player_actor.tell(["toggle_mute"])
        self.update()
        pass

    def adjust_volume(self, delta):
        self._player_actor.tell(["adjust_volume", delta])
        self.update()
        pass

    def handle_key(self, key):
        if key == " ":
            self.pause()
        elif key == "n":
            self.next_song()
        elif key == "l":
            self.rate(1)
        elif key == "u":
            self.rate(0)
        elif key == "x":
            self.rate(-1)
            self.next_song()
        elif key == "q":
            raise urwid.ExitMainLoop()
        elif key == "c":
            self._output_widget.contents = []
        elif key == "h":            
            help_str = "\n".join([
                "Key help:",
                "  [space] for pausing/resuming.",
                "  [-|+/=] for adjusting the volume.",
                "  [m] for muting.",
                "  [n] for next song.",
                "  [l] for liking the song.",
                "  [u] for canelling liking the song.",
                "  [x] for unliking the song and go to next song.",
                "  [c] for cleaning the logs.",
                "  [q] for exiting."])
            self.log(help_str)
        elif key == "=" or key == "+":
            self.adjust_volume(5)
        elif key == "-":
            self.adjust_volume(-5)
        elif key == "m":
            self.toggle_mute()
        elif self._debug:
            self.log("Unknown key [{}]".format(key))
            pass
        pass

    def update(self):
        data = self._player_actor.ask(["get_status"])
        pos = data[0]
        length = data[1]
        vol = data[2]
        percent = data[3]
        if pos is not None:
            self._last_stopped_time = None
            self._title_widget.set_text(self._current_song_title if self._current_song_title is not None else self._player.filename)
            self._progress_widget.set_text("{pos}/{length} ({percent}%)".format(
                pos = "-" if pos is None else ("%.02f" % pos),
                length = "-" if length is None else ("%.02f" % length),
                percent = "-" if percent is None else percent
            ))
            self._volume_widget.set_text("Volume: {}%".format(vol))
            return True
        else:
            return False
        pass

    def refresh(self, loop, data):
        """
        Periodic work:

        1. Update UI about the current state
        2. If the player stops for a long time (> switch_threshold), switch to next song
        """
        if not self.update():
            now = time.time()
            if self._just_started:
                self._just_started = False
                self.start()
            elif self._last_stopped_time is not None and \
                 now - self._last_stopped_time > self._switch_threshold:
                self.next_song()
            elif self._last_stopped_time is None:
                self._last_stopped_time = now
                pass
            pass
        loop.set_alarm_in(self._refresh_interval, self.refresh)
        pass

    def run(self):
        self._loop = urwid.MainLoop(self.frame, unhandled_input = self.handle_key)
        self._loop.set_alarm_in(self._refresh_interval, self.refresh)
        try:
            self._loop.run()
        except Exception as e:
            print(e)
            pass
        self._player_actor.stop()
        self._proc.kill()
