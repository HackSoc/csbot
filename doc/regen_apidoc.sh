#!/bin/bash
rm -rf api
exec sphinx-apidoc --separate --output-dir=api/ ../csbot ../csbot/test ../csbot/test_broken ../csbot/plugins_broken
