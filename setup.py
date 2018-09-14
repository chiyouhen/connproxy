#! /usr/bin/env python

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="connproxy",
    version="0.0.1",
    author="chiyouhen",
    author_email="chiyouhen@gmail.com",
    description="connproxy",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/chiyouhen/connproxy",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.7",
        "License :: OSI Approved :: GPL License",
        "Operating System :: OS Independent",
    ],
)
