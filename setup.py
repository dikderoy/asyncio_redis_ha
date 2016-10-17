#!/usr/bin/env python
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup
import sys

install_requires = ['asyncio-redis==0.14.3']
if sys.version_info <= (3, 4):
    install_requires += ['asyncio']

setup(
    name='asyncio_redis_ha',
    author='Roman Bulgakov',
    version='0.1.1',
    license='MIT',
    url='https://github.com/dikderoy/asyncio_redis_ha',

    description='Redis/Sentinel High Availability package for asyncio-redis',
    classifiers=[
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Database :: Front-Ends',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    long_description=open("README.rst").read(),
    keywords='redis sentinel high-availability client asyncio',

    packages=['asyncio_redis_ha'],
    install_requires=install_requires,
    # extra_require={
    #     'hiredis': ['hiredis'],
    # }
)
