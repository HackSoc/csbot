#!/usr/bin/env python
import unittest
import sys

suite = unittest.TestLoader().discover('csbot/test', top_level_dir='.')
result = unittest.TextTestRunner().run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
