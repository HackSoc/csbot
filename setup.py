import setuptools


setuptools.setup(
    name='csbot',
    version='0.3.0',
    author='Alan Briolat',
    author_email='alan@briol.at',
    url='https://github.com/HackSoc/csbot',
    packages=['csbot', 'csbot.plugins'],
    package_dir={'': 'src'},
    classifiers=[
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    install_requires=[
        'click>=6.2,<7.0',
        'pymongo>=4.0.1',
        'requests>=2.9.1,<3.0.0',
        'lxml>=2.3.5',
        'aiogoogle>=0.1.13',
        'isodate>=0.5.1',
        'aiohttp>=3.5.1,<4.0',
        'async_generator',
        'attrs>=19.1,<20',
        'toml',
        'schematics',
        'rollbar',
    ],
    entry_points={
        'console_scripts': [
            'csbot = csbot.cli:main',
            'csbot_util = csbot.cli:util',
        ],
    },
)
