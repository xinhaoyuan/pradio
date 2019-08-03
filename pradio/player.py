import subprocess
import json
import mplayer
import time
import urwid
import pykka
import sys
import threading
import queue
import logging

# Use separate thread to poll status to avoid delays
class MplayerPollingThread(threading.Thread):

    def __init__(self, args, mplayer_actor, player):
        super(MplayerPollingThread, self).__init__()
        self._mplayer_actor = mplayer_actor
        self._player = player
        self._refresh_interval = args.refresh_interval
        self.queue = queue.SimpleQueue()
        self.running = True
        pass

    def run(self):
        now = time.time()
        while self.running:
            try:
                # Process at least one action before timeout, but no more. (Is this the best way?)
                processed = False
                while now + self._refresh_interval > time.time() or not processed:
                    task = self.queue.get(block = True, timeout = max(0, now + self._refresh_interval - time.time()))
                    processed = True
                    if task[0] == "play":
                        self._player.loadfile(task[1])
                    elif task[0] == "toggle_mute":
                        self._player.mute = not self._player.mute
                    elif task[0] == "adjust_volume":
                        self._player.volume = min(100, max(0, self._player.volume + task[1]))
                    elif task[0] == "pause":
                        self._player.pause()
                    pass
            except queue.Empty:
                pass
            now = time.time()
            self._mplayer_actor.tell(
                [ "update",
                  self._player.time_pos,
                  self._player.length,
                  self._player.percent_pos,
                  self._player.volume
                ])
            pass
        pass

    pass

class MplayerActor(pykka.ThreadingActor):

    def __init__(self, args):
        super(MplayerActor, self).__init__()
        self._debug = args.debug
        self._refresh_interval = args.refresh_interval
        self._cache_timepos = None
        self._cache_length = None
        self._cache_volume = None
        self._cache_percent = None
        self._thread = None

    def on_receive(self, msg):
        ret = None

        if msg[0] == "set_thread":
            self._thread = msg[1]
        if msg[0] == "update":
            self._cache_timepos = msg[1]
            self._cache_length = msg[2]
            self._cache_percent = msg[3]
            self._cache_volume = msg[4]
        if msg[0] == "play":
            self._cache_timepos = None
            self._cache_length = None
            self._cache_volume = None
            self._cache_percent = None
            self._thread.queue.put(msg)
        elif msg[0] == "get_status":
            ret = (self._cache_timepos, self._cache_length, self._cache_volume, self._cache_percent)
        elif msg[0] == "toggle_mute":
            self._thread.queue.put(msg)
        elif msg[0] == "adjust_volume":
            self._thread.queue.put(msg)
        elif msg[0] == "pause":
            self._thread.queue.put(msg)
        else:
            pass

        return ret

    pass

def channel_button(c, player):
    button = urwid.Button(c["name"])
    urwid.connect_signal(button, "click", lambda x : player.choose_channel(c["name"], c["id"]))
    return urwid.AttrMap(button, None, focus_map='reversed')

def channel_menu(channels, player):
    body = [ urwid.Text("Choose channel:"), urwid.Divider() ]
    body.extend([ channel_button(c, player) for c in channels ])
    return urwid.ListBox(urwid.SimpleFocusListWalker(body))

class Player:

    def __init__(self, args):
        self._song_format = args.song_format
        self._refresh_interval = args.refresh_interval
        self._switch_threshold = args.switch_threshold
        self._proc = subprocess.Popen(args.args,
                                stdin = subprocess.PIPE,
                                stdout = subprocess.PIPE)
        self._debug = args.debug
        if args.debug:
            self._player = mplayer.Player()
        else:
            self._player = mplayer.Player(stderr = subprocess.DEVNULL)
        self._actor = MplayerActor.start(args)
        self._helper_thread = MplayerPollingThread(args, self._actor, self._player)
        self._actor.ask([ "set_thread", self._helper_thread ])
        self._helper_thread.start()
        self._title_widget = urwid.Text("", align = "center")
        self._progress_widget = urwid.Text("", align = "center")
        self._volume_widget = urwid.Text("", align = "center")
        self._output_widget = urwid.Pile([])
        self._output_container = urwid.Filler(self._output_widget, valign = 'top')
        self._main_placeholder = urwid.WidgetPlaceholder(self._output_container)
        self._frame = urwid.Frame(
            header= urwid.Pile([
                self._title_widget,
                self._progress_widget,
                self._volume_widget,
                urwid.Divider("-"),
            ]),
            body = self._main_placeholder,
            focus_part = 'header')
        self._current_song_title = None
        self._last_stopped_time = None
        self._loop = None
        self._channel_id = None
        self._choosing_channel = False
        self._try_exiting = False
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
            logging.exception("Exception while rating the current song")
            self._last_log.set_text("Exception while rating the current song: %s" % str(e))
            pass
        pass

    def next_song(self):
        """
        Query for the next song, set up mplayer, and generate the title based on the returned data.
        """
        self._last_stopped_time = None
        self.log("Requesting the next song ...")
        try:
            req = { "type" : "cmd_next" }
            if self._channel_id is not None:
                req["channel_id"] = self._channel_id
            self._proc.stdin.write(json.dumps(req).encode("utf-8"))
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

            self._actor.tell(["play", url])
            self.update()
        except Exception as e:
            logging.exception("Exception while getting the next song")
            self.log("Exception while getting the next song: %s" % str(e))
            pass
        pass

    def toggle_mute(self):
        self._actor.tell(["toggle_mute"])
        self.update()
        pass

    def adjust_volume(self, delta):
        self._actor.tell(["adjust_volume", delta])
        self.update()
        pass

    def toggle_choose_channel(self):
        if self._choosing_channel:
            self._main_placeholder.original_widget = self._output_container
            self._choosing_channel = False
            return

        channels = None
        try:
            req = { "type" : "cmd_list_channels" }
            self._proc.stdin.write(json.dumps(req).encode("utf-8"))
            self._proc.stdin.write(b"\n")
            self._proc.stdin.flush()
            resp = json.loads(self._proc.stdout.readline().decode("utf-8"))
            assert(resp["type"] == "reply_ok")
            assert("channels" in resp)

            channels = resp["channels"]
        except Exception as e:
            logging.exception("Exception while getting the channel list")
            self.log("Exception while getting the channel list: %s" % str(e))
            return

        self._choosing_channel = True
        menu = channel_menu(channels, self)
        self._main_placeholder.original_widget = urwid.Overlay(
            menu,
            self._output_widget,
            align='center', width=('relative', 80),
            valign='middle', height=('relative', 80)
        )
        self._frame.set_focus("body")
        pass

    def pause(self):
        self._actor.tell(["pause"])

    def choose_channel(self, name, channel_id):
        if not self._choosing_channel:
            return

        self._channel_id = channel_id
        self._choosing_channel = False
        self._main_placeholder.original_widget = self._output_container
        self.log("Choose channel {}: {}".format(name, channel_id))
        self.next_song()

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
            if self._choosing_channel:
                self.toggle_choose_channel()
            elif not self._try_exiting:
                self._try_exiting = True
                self.log("Press [q] again to exit.")
            else:
                raise urwid.ExitMainLoop()
        elif key == "c":
            self.toggle_choose_channel()
        elif key == "/":
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
                "  [c] for changing the channel.",
                "  [/] for cleaning the logs.",
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

        if key != "q":
            self._try_exiting = False
        pass

    def update(self):
        data = self._actor.ask(["get_status"])
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
        self._loop = urwid.MainLoop(self._frame, palette=[('reversed', 'standout', '')], unhandled_input = self.handle_key)
        self._loop.set_alarm_in(self._refresh_interval, self.refresh)
        try:
            self._loop.run()
        except Exception as e:
            logging.exception("Exception in the main loop")
            pass
        self._helper_thread.running = False
        self._helper_thread.join()
        self._actor.stop()
        self._proc.kill()
