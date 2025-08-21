from setuptools import setup

setup(name="pygrbl_streamer",
      version="1.0.0",
      author="Beltrán Offerrall",
      py_modules=["grbl_streamer"],
      install_requires=["pyserial"],
      python_requires=">=3.7"
      )

