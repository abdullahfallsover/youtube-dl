#!/usr/bin/env python
# coding: utf-8
"""
Setup script for youtube_dl_extractors package.

This package contains all site-specific extractors for youtube-dl.
It is distributed separately from youtube-dl core to allow:

1. Core youtube-dl to be distributed via app stores
2. Independent updates of extractors
3. Users to install only extractors they need
"""

from __future__ import print_function

from setuptools import setup, find_packages

__version__ = '2024.01.01'

setup(
    name='youtube-dl-extractors',
    version=__version__,
    description='Site-specific extractors for youtube-dl',
    long_description=open('README.md').read() if __import__('os').path.exists('README.md') else '',
    long_description_content_type='text/markdown',
    url='https://github.com/ytdl-org/youtube-dl',
    author='youtube-dl contributors',
    author_email='ytdl@yt-dl.org',
    license='Unlicense',
    packages=find_packages(),
    python_requires='>=2.6',
    install_requires=[
        'youtube-dl>=2024.01.01',
    ],
    entry_points={
        'youtube_dl.plugins.extractor': [
            'extractors = youtube_dl_extractors.extractors',
        ],
    },
    classifiers=[
        'Topic :: Multimedia :: Video',
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'License :: Public Domain',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
