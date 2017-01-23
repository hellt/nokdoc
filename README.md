<p align="center">
  <img src="http://img-fotki.yandex.ru/get/41743/21639405.11d/0_8bea9_ab188260_orig.jpg" alt="Why NokDoc?"/>
</p>
# About
NokDoc CLI Tool built to interact with Nokia (fALU) [documentation portal](https://support.alcatel-lucent.com) in a CLI fashion.

It exposes to a user a set of commands and options for the following
high-level tasks:
- Build an HTML document with a list of all documentation entries for selected product/release. [Example](https://nokdoc.github.io/docs/nuage/nokdoc__NUAGE__4.0.R6.1.html);
- Download a zipped collection with documents for selected product/release;
- Query the documentation server about available releases for a given product/release.

Check out [NokDoc Lib](https://nokdoc.github.io) site where HTML files grabbed by NokDoc were manually aggregated per product family.

# How to install NokDoc CLI Tool
A proper way to install Python CLI tools would be by using a virtual environment.
One of the main reasons to do so is to keep your system-packages clean and consistent. I urge you to embrace the power of [pipsi](https://github.com/mitsuhiko/pipsi) tool that capable of install any Python CLI tool in a separate virtualenv and take care of all the internal links.

If you do not care much about your system-wide Python packages you can skip pipsi installation and install NokDoc with plain pip: `pip3 install nokdoc` (just make sure to use pip for python3).

## Installing pipsi
### Prerequisites
You have to have `virtualenv` package installed to install pipsi. If have a clean system with no virtualenv or pip installed the easiest way to install necessary things would be:
```
## Debian-based. For example Ubuntu 14.0.5
sudo apt-get update
sudo apt-get install python3-pip
sudo pip3 install virtualenv

## RHEL-based (Centos 7)
sudo yum -y install https://centos7.iuscommunity.org/ius-release.rpm
sudo yum install python35u
sudo yum install python35u-pip
sudo pip3.5 install virtualenv
```
### Installing pipsi
Then use installation script provided via pipsi github package
```shell
curl https://raw.githubusercontent.com/mitsuhiko/pipsi/master/get-pipsi.py | python3
```
Pay attention to the python interpreter version after the pipe. NokDoc has been tested with `python3` that is why `python3` interpreter should be used to install pipsi. On your installation there might not be `python3` but `python3.5` executable. Yes, it works with `python2.7`, but I do not test it.

Also ensure that you have met pipsi requirement to add additional path to your `PATH` env. variable. On Mac OS and Ubuntu systems pipsi might tell you how to do that in the end of its installation process:
```shell
Warning:
  It looks like /home/vagrant/.local/bin is not on your PATH so pipsi will
  not work out of the box.  To fix this problem make sure to
  add this to your .bashrc / .profile file:

  export PATH=/home/vagrant/.local/bin:$PATH

# adding new path to $PATH
echo "export PATH=/home/vagrant/.local/bin:$PATH" >> ~/.profile
# (re-open your session to changes take effect)
# or issue "source ~/.profile"
```

## Installing NokDoc
Once you have pipsi installed you can safely install NokDoc:
```
pipsi install nokdoc
```

# How to use NokDoc
NokDoc has built-in help:
```
rdodin@vbox:~$ nokdoc
Usage: nokdoc [OPTIONS] COMMAND [ARGS]...

  NokDoc CLI Tool is exposing a set of commands to interact with Nokia
  documentation portal. It offers CLI experience for tasks like - getting
  links to the docs aggregated into HTML file - downloading docs collections
  automatically

  It works for authorized users and guests.

Options:
  -l, --login TEXT  Put in your login to get access to thedocumentation
                    requiring authorization
  -p, --proxy TEXT
  --help            Show this message and exit.

Commands:
  getdocs   Downloads documentation collection for a...
  getlinks  Gets a single HTML file with links to the...
  showrels  Lists all available releases for a given...
```
Let's explore what can be done with NokDoc.
### Guest access and logged users
Nokia documentation falls into two categories: one that can be accessed without registration and other that will ask for a login.
NokDoc allows a user to work as a guest (i.e. non logged in) and in authorized mode.

Unauthorized users will be able to receive only those documents which are open.

If you have a login to the documentation portal then simply pass your login to run NokDoc commands in the authorized mode with optional `-l <username>` parameter:
```
nokdoc -l <username> COMMAND [OPTIONS]
```
NokDoc will prompt you for your password and authorize you with the documentation server.
## Getting HTML file with links to documentation
One feature of NokDoc is to build HTML files with the direct links to the documentation articles. An example of such a page can be found [here](https://nokdoc.github.io/docs/7750sr/nokdoc__7750SR__14.0.html). The idea was to save such files locally to keep the whole documentation at hand.
```
nokdoc -l <username> getlinks -p <product_name> -r <release>
```
Each command has its own help section with optional parameters explained:
```
rdodin@vbox:~$ nokdoc getlinks --help
Usage: nokdoc getlinks [OPTIONS]

  Gets a single HTML file with links to the documetation elements for a
  given product.

Options:
  -p, --product [1350oms|5620sam|7210sas|7450ess|7705sar|7750sr|7850-8vsg|7850vsa|7850vsg|7950xrs|nuage|nuage-vns|nuage-vsp|vsr]
                                  [required]
  -r, --release TEXT              Release version, use "showrels" command to
                                  list them
  -f, --format [pdf|html|zip]     Specify documentation format to fetch.If
                                  unspecified -> all types will be collected.
  -s, --sort [title|issue_date]   Choose sorting key. Defaults to "title"
  --help                          Show this message and exit.
```
As you see there are some filtering options, though in practice you most probably will need just `--product` and `--release` to filter docs for a particular release of a given product:
```
# this will build an HTML file with docs available for everyone
# since no login option was passed
nokdoc getlinks -p 7750sr -r 14.0
```
## Downloading documentation collection
Another feature of NokDoc is being able to generate request to the documentation server for collection generation and automatically download it once it is available.

This makes for those product families who has no zip collections provided as a part of documentation set.
```
# for example this one will try to download a collection
# for nuage-vns release 4.0.R4 (pdf files only)
nokdoc -l rdodin getdocs -p nuage-vns -r 4.0.r4 -f pdf
```
Again, options can be explored via built-in help page:
```
rdodin@vbox:~$ nokdoc getdocs --help
Usage: nokdoc getdocs [OPTIONS]

  Downloads documentation collection for a given product family. Optionally
  specify release version to fetch OPtionally specify format of the docs to
  fetch

  Currently supported products: nuage, nuage-vsp, nuage-vns

Options:
  -p, --product [1350oms|5620sam|7210sas|7450ess|7705sar|7750sr|7850-8vsg|7850vsa|7850vsg|7950xrs|nuage|nuage-vns|nuage-vsp|vsr]
                                  [required]
  -r, --release TEXT              Release version, use "showrels" command to
                                  list them
  -f, --format [pdf|html|zip]     Specify documentation format to fetch.If
                                  unspecified -> all types will be collected.
  --help                          Show this message and exit.
```
## Exploring available releases
Obviously almost everytime each command refers to some release for a given product. Yet it is not obvious what releases and in what numbering convention are available to pass into `--release` option.

For this purpose another small command was introduced:
```
# listing all available releases for 7750SR family
[vagrant@localhost ~]$ nokdoc showrels -p 7750sr

  ####### SHOW RELEASES #######
  Checking available releases...
  Available releases for 7750sr family: 4.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, Arbor6.0, Arbor7.0, Arbor7.5, ArborCP5.7, ArborCP5.8p3, ArborCP5.8p4, ArborTMS5.6.P5, ArborTMS5.7.P4, ArborTMS5.8, arborTMS5.8P4, ArborTMS5.8P5, MG3.1, MG4.0, MG5.0, MG6.0, MG7.0, MG8.0
```
# Contribution or requests?
If you would like to contribute feel free to clone this repo and come up will pull request.

If you have some opinions regarding this tool or would like to propose a feature request -- create an **Issue** and we will have a chat about it.
