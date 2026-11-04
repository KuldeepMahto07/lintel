# -*- coding: utf-8 -*-
"""Connect this model to Lintel (click again to disconnect)."""
__title__ = "Lintel"
__doc__ = "Connect the open model to Lintel: live rule checks, and approved fixes applied as one undo step."

import os
import sys

# hosts/revit/Lintel.extension/Lintel.tab/Lintel.panel/Lintel.pushbutton -> hosts/revit
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))
import lintel_revit  # noqa: E402

lintel_revit.toggle(__revit__)  # noqa: F821  (pyRevit provides __revit__, the UIApplication)
