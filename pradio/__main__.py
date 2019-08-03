import argparse
import logging
from .player import Player

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--song-format", dest = "song_format", default = "{title} - {singers} [{album}]")
    parser.add_argument("--refresh-interval", dest = "refresh_interval", default = 1)
    parser.add_argument("--switch-threshold", dest = "switch_threshold", default = 10)
    parser.add_argument("--debug", dest = "debug", action = "store_true")
    parser.add_argument("--use-mplayer", dest = "use_mplayer", action = "store_true")
    parser.add_argument("--mplayer-exec", dest = "mplayer_exec")
    parser.add_argument("--log")
    parser.add_argument("args", nargs = "+")
    args = parser.parse_args()

    if args.log is not None:
        logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s', filename = args.log, filemode = "w")
        pass

    if args.use_mplayer and args.mplayer_exec is not None:
        import mplayer
        mplayer.Player.exec_path = args.mplayer
    
    Player(args).run()
    pass

if __name__ == "__main__":
    main()
