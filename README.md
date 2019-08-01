# PRadio

An overly simple, easily extensible radio player through process pipes.

This is not intended as a full-featured player.
Instead, it is a POC for PRadio protocol.
Hopefully there will be plugin in main-stream players using the protocol.

Author: Xinhao Yuan <xinhaoyuan@gmail.com>

## Protocol

Each command and reply is a JSON object with `type` field.
The piped process should replyed with `type` field either `reply_ok` or `reply_error`.

### Commands

- `type = "cmd_next"`

  Get the next song from the radio.
  
  Reply: `type = "reply_ok"; data = { title = (string), album = (string), singers = [(string)], url = (string) }`
  `data.url` is required. Others are not.

- `type = cmd_rate, rating = (int)`

  Rate the current song.
  Currently it only matters for the sign of the rating. Positive = like; negative = dislike; 0 = erase rating.

  Reply: `type = "reply_ok"`

TODO: list and change channels

When command replys with `type = "reply_error"`, `message` and `details` fields are optional strings of extra information.
