import getpass
import webbrowser

import prompter
from cached_property import cached_property
from jira import JIRA
from jira.exceptions import JIRAError
from jira.resilientsession import ResilientSession


class ResilientSessionWithAuthCheck(ResilientSession):
    """
    Extends the python-jira ResilientSession to reset our session's cookies when auth epxires.
    """

    def __init__(self, jira_client, resilient_session_obj):
        """
        Constructor.

        Copy our attrs to be equivalent to the ResilientSession that was already
        created. We'll end up with an identical instance of ResilientSession, but the
        __recoverable() method defined below will be overriden.

        We store the args/kwargs that were used to instantiate the JIRA client so that we can
        create a new client instance with the same properties in the get_new_cookies() method.
        """
        self.__dict__ = resilient_session_obj.__dict__.copy()
        self._client = jira_client

    def get_new_cookies(self):
        """
        Re-init a JIRA client and grab new cookies from it.

        There is a lot of logic in the JIRA class __init__ method to handle creating the
        authenticated session, so it's easier to just init the instance and pull the cookies
        into our current session.
        """
        self._client.connect()
        self.cookies = new_client.session.cookies  # noqa

    def _ResilientSession__recoverable(self, response, *args, **kwargs):
        """
        Override the ResilientSession __recoverable() method.

        Override the retry logic to get new cookies if a 401 is hit.

        The python-jira ResilientSession retries the http request when a 401 is hit, but does
        not try to refresh the auth session.
        """
        if hasattr(response, "status_code") and response.status_code == 401:
            print("Session expired, attempting to refresh...")
            self.get_new_cookies()
        return super()._ResilientSession__recoverable(response, *args, **kwargs)


class JiraClient(JIRA):
    def __init__(self, config):
        self.config = config

    def _create_kerberos_session(self, *args, **kwargs):
        """
        Little hack to get auth cookies from JIRA when using kerberos, otherwise
        queries to other URLs hit a 401 and are not handled properly for some
        reason

        https://stackoverflow.com/questions/21578699/jira-rest-api-and-kerberos-authentication
        """
        super()._create_kerberos_session(*args, **kwargs)
        print("Attempting to authenticate with kerberos...")
        r = self._session.get("{}/step-auth-gss".format(self._options["server"]))
        if r.status_code == 200:
            print("Authenticated successfully")

    @cached_property
    def userid(self):
        return self.myself()["key"]

    def _handle_init(self, **kwargs):
        try:
            super().__init__(**kwargs)
        except JIRAError as e:
            if "CAPTCHA_CHALLENGE" in e.text:
                print("Too many failed login attempts, answering a CAPTCHA is required")
                if prompter.yesno(f"Open a browser to log in to '{self.config.url}'?"):
                    url = f"{self.config.url}/login.jsp?nosso"
                    webbrowser.open_new(url)
                input("Hit ENTER here once you have logged in via a web browser")
                super().__init__(**kwargs)
            else:
                raise

    def connect(self):
        config = self.config

        print("Connecting to jira at", config.url)
        kwargs = {}
        kwargs["validate"] = False

        if config.basic_auth:
            print("Using basic authentication")
            password = config.password or getpass.getpass("Enter your JIRA password: ")
            kwargs["basic_auth"] = (config.username, password)
        else:
            print("Using kerberos authentication")
            kwargs["kerberos"] = True
            kwargs["kerberos_options"] = {"mutual_authentication": "DISABLED"}

        kwargs["options"] = {"server": self.config.url}
        if config.ca_cert_path:
            kwargs["options"]["verify"] = config.ca_cert_path
        if self.config.verify_ssl is False:
            print("Warning: SSL certificate verification is disabled!")
            kwargs["options"]["verify"] = False
            # Disable ssl validation warnings, we gave one warning already ...
            from urllib3.exceptions import InsecureRequestWarning
            from requests.packages.urllib3 import disable_warnings

            disable_warnings(category=InsecureRequestWarning)

        self._handle_init(**kwargs)

        print(f"\nLogged in to '{self.config.url}' as user '{self.userid}'")

        # Overrides the JIRA session with our own version of ResilientSession.
        self._session = ResilientSessionWithAuthCheck(self, self._session)

    @property
    def session(self):
        return self._session
