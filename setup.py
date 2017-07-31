from setuptools import setup, find_packages

setup(
    name='nokdoc',
    version='0.3.0',
    description="CLI Tool for interaction with Nokia doc portal",

    # Application author details:
    author="Roman Dodin",
    author_email="dodin.roman@gmail.com",

    # py_modules=['nokdoc'],
    packages=find_packages(),
    include_package_data=True,

    install_requires=[
        'Click',
        'requests',
        'certifi',
        'jinja2',
        'tqdm',
        'natsort',
        'pyyaml'
    ],
    entry_points='''
        [console_scripts]
        nokdoc=nokdoc.nokdoc:cli
    ''',
)
