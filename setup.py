#!/usr/bin/env python
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup
import sys

install_requires = ['asyncio_redis']
if sys.version_info <= (3, 4):
    install_requires += ['asyncio']

setup(
    name='asyncio_redis_ha',
    author='Roman Bulgakov',
    version='0.0.1',
    license='LICENSE',
    url='https://github.com/dikderoy/asyncio_redis_ha',

    description='Sentinel support for asyncio Redis client',
    long_description=open("README.md").read(),
    packages=['asyncio_redis_ha'],
    install_requires=install_requires,
    extra_require={
        'hiredis': ['hiredis'],
    }
)
