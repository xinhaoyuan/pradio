from setuptools import setup

setup(
    name = "pradio",
    description = "An overly simple, easily extensible radio player through process pipes",
    version = "0.2.2",
    packages = [ "pradio" ],
    include_package_data = True,
    author = "Xinhao Yuan",
    author_email = "xinhaoyuan@gmail.com",
    url = "https://github.com/xinhaoyuan/pradio",
    license = "Apache License 2.0",
    install_requires = [ "urwid", "pykka >= 2.0.0" ],
    extras_require = { "mplayer" : [ "mplayer.py" ], "vlc" : [ "python-vlc" ] },
    long_description = open("README.md").read(),
    long_description_content_type = "text/markdown",
    entry_points={
        "console_scripts" : [
            'pradio = pradio.__main__:main'
        ]
    },
)
