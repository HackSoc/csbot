#!/bin/bash
rm -rf api
exec sphinx-apidoc --separate --output-dir=api/ ../src/csbot ../src/plugins_broken
