#!/usr/bin/env python3
"""The one exception the pipeline raises at people.

`SystemExit` used to be raised straight from library functions -- 48 of
them. It inherits from BaseException, not Exception, which has three
costs: a caller writing `except Exception` is bypassed without knowing
it; a function called by eleven programs decides on its own that the
whole process should end; and `asrmt_batch`, which wants to skip a
failing episode and carry on, had to catch a BaseException to do
ordinary flow control.

So the pipeline raises `PipelineError` instead, and nothing converts it
back at the CLI boundary (使用者裁定). An unhandled one prints its
traceback and exits 1: the stack names which check fired and who called
it, and when a batch stops mid-run that is worth more than a tidy
one-line message.
"""


class PipelineError(Exception):
    """Something the operator, the store or an external service got wrong.

    A *declared* failure -- which is what lets a batch tell "this episode
    cannot be done, try the next one" apart from "something unforeseen
    happened, stop and look". Every message is written for a human: it
    names the episode, the file or the value that was wrong.
    """
