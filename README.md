simplejira

COMPLETELY A WORK IN PROGRESS

A CLI-based tool for making agile in jira a little more... simple

This is a project used by the Red Hat CloudForms QE team to make their life easier. It might be useful for you too.

Make sure you have these dependencies installed for Python 2 (e.x., on fedora):

` $ dnf install gcc redhat-rpm-config python2-devel krb5-devel which binutils`

If you're using Python 3, you'll need to install `python3-devel` instead of `python2-devel`.

Install with:

` $ pip install -r requirements.txt`

If you have issues with SSL validation, the config supplies a field for the CA trust cert path. You can also comment
out this line to use your system default. On Fedora, you can `dnf install python-requests` to install a patched version
of requests that is already pointed toward the Fedora CA cert bundle by default.
