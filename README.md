# jiraprompt

**COMPLETELY A WORK IN PROGRESS**

A CLI-based tool that gives quick access to basic agile workflows for a JIRA board. jiraprompt runs on Python
 3.6 and higher.

This is a project used by the Red Hat CloudForms QE team to make their life easier. It might be
useful for you too.

## Dependencies
You'll need the Python headers and the Kerberos headers installed in order to install jiraprompt's
dependencies.

### Fedora

```
$ sudo dnf install gcc redhat-rpm-config python3-devel krb5-devel which binutils
```

### Debian

```
$ sudo apt install build-essential python3-dev libkrb5-dev
```

## Installing

To install jiraprompt and the rest of its dependencies, it is recommended you set up a virtual environment

```
$ python3.6 -m venv env
```

The package is available on pypi, so you can simply run:

```
$ env/bin/pip install jiraprompt
```

Alternatively, you can install from source with:

```
$ env/bin/pip install -r requirements.txt
$ env/bin/python setup.py install
```

## Running

To run jiraprompt, just run the `jiraprompt` command in the `bin` directory of your virtual
environment.

```
$ env/bin/jiraprompt
```

The first time you run jiraprompt, it will set up a new configuration for you.

## Development

If you want to hack on jiraprompt, you can do a development install with `pip` instead of the
install command above, like so:

```
$ env/bin/pip install -e .
```

## SSL Validation

If you have issues with SSL validation, the config supplies a field for the CA trust cert path. You
can also comment out this line to use your system default. On Fedora, you can run
`dnf install python-requests` to install a patched version of requests that is already pointed
toward the Fedora CA cert bundle by default.
