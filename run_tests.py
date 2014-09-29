#!/usr/bin/env python
import unittest

suite = unittest.TestLoader().discover('csbot/test', top_level_dir='.')
unittest.TextTestRunner().run(suite)
