# -*- coding: utf-8 -*-
"""Studio (SPEC 6절 3단계): a non-coding artist talks (Korean text + images); an agent calls small SDK tools that
*propose* changes; the artist applies or corrects them; every applied change is a version.

    config.py   model id and data locations (one place)
    session.py  versions, proposals, pending approvals (A-02, A-05, A-06)
    diff.py     what changed between two worlds (D-04, and the "이렇게 이해했다" summary)
    tools.py    tool schemas (strict) + executor
    agent.py    the conversation loop over the Anthropic Messages API (client injected)
    vocab.py    per-artist vocabulary (A-04) -- stored outside the repository, never sent to the browser
    board.py    variant board (D-01..D-04)
    server.py   `python3 -m worldengine studio` -- the page a phone or PC opens; the API key stays here
"""
