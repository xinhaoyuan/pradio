import argparse
from .player import Player

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--song-format", dest = "song_format", default = "{title} - {singers} [{album}]")
    parser.add_argument("--refresh-interval", dest = "refresh_interval", default = 1)
    parser.add_argument("--switch-threshold", dest = "switch_threshold", default = 10)
    parser.add_argument("--debug", dest = "debug", action = "store_true")
    parser.add_argument("args", nargs = "+")
    args = parser.parse_args()
    
    Player(args).run()
    pass

if __name__ == "__main__":
    main()
