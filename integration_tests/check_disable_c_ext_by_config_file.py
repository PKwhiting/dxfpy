# This test is hard to do in pytest!

from pathlib import Path
import dxfpy

p = Path(__file__).with_name("disable.ini")

dxfpy.options.read_file(str(p))
print(f"disable C-Extension (should be True): {dxfpy.options.disable_c_ext}")
assert dxfpy.options.disable_c_ext is True

# It is not possible to deactivate the C-extension by a user config file
# loaded after the dxfpy import, because the setup process of dxfpy is already
# finished.
print(f"using C-Extension (should be True): {dxfpy.options.use_c_ext}")
assert dxfpy.options.use_c_ext is True
