"""Server application for the integration test. Common part for all protocols."""

import logging
import sys

import test_libs.library as lib
import test_libs.parameters as param

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

served_objects = {
    "TargetClass": lib,
    "Param": param,
}
