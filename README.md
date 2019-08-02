# PRadio

An overly simple, easily extensible radio player through process pipes.

This is not intended as a full-featured player.
Instead, it is a POC for PRadio protocol.
Hopefully there will be plugin in main-stream players using the protocol.

Author: Xinhao Yuan <xinhaoyuan@gmail.com>

## Protocol

Each command and reply is a JSON object with `type` field.
The piped process should reply with `type` field either `reply_ok` or `reply_error`.

### Commands

- `type = "cmd_next", (channel_id = (int))`

  Change channel if specified. Get the next song from the radio.

  Reply: `type = "reply_ok", id = (any), data = { (title = (string), album = (string), singers = [(string)]), url = (string) }`
  `data.url` is required. Others are not.

- `type = "cmd_rate", id = (any), rating = (int)`

  Rate the song with the specified internal id.
  If no id is specified, rate the current song.
  Currently it only matters for the sign of the rating. Positive = like; negative = dislike; 0 = erase rating.

  Reply: `type = "reply_ok"`

- `type = "cmd_list_channels"`

  Reply: `type = "reply_ok", channels = [{ name = (string), id = (int) }]`

When command replys with `type = "reply_error"`, `message` and `details` fields are optional strings of extra information.
