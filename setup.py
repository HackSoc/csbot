from distutils.core import setup


setup(
    name='csbot',
    version='0.1',
    author='Alan Briolat',
    author_email='alan@briol.at',
    url='https://github.com/HackSoc/csbot',
    packages=['csbot', 'csbot.plugins'],
    package_dir={'': 'src'},
    classifiers=[
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    entry_points={
        'console_scripts': [
            'csbot = csbot:main',
        ],
    },
)
