"""
Copyright (C) 2021 Erin Morelli.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see [https://www.gnu.org/licenses/].
"""

import os
from datetime import datetime

import click
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from requests import Session, RequestException

from sqlalchemy_utils import EmailType
from sqlalchemy.dialects.sqlite import BLOB
from sqlalchemy import Table, Column, String, DateTime, func
from sqlalchemy.exc import MultipleResultsFound, NoResultFound

from mfm_fan_cult.content_types import login_user


class FanCultContent:
    """Base content class that also provides account access."""
    command = 'account'
    model_name = command
    # URLs for making requests
    base_url = 'https://myfavoritemurder.com'
    login_url = f'{base_url}/login'
    # Copyright and logo info
    logo = 'https://emorel.li/dl/fc_logo.png'
    copyright = {
        'name': 'Exactly Right',
        'email': 'exactlyrightmedia@gmail.com'
    }
    # User agent for HTTP requests
    user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) ' \
                 'Gecko/20100101 Firefox/89.0'
    # Common headers for HTTP requests
    headers = {
        'User-Agent': user_agent,
        'Referer': base_url,
        'Origin': base_url
    }
    # Set CLI details for account management
    command_help = 'Manage your Fan Cult account.'
    commands = ['login', 'update', 'show']

    def __init__(self, manager):
        """Setup details for content class."""
        self.manager = manager
        self.session = Session()
        self.db = self.manager.get_session()
        self.model = self.manager.models.get(self.model_name)

    def _get_account(self):
        """Locate an account in the database."""
        model = self.manager.models.get('account')
        try:
            account = self.db.query(model).one()
        except NoResultFound:
            # Ask user to login
            self.manager.warning('Please login to your account first.')
            return None
        except MultipleResultsFound:
            # List all available accounts
            click.echo('Multiple accounts found:')
            all_accounts = self.db.query(model).all()
            for idx, acct in enumerate(all_accounts):
                click.echo(f' [{idx}] {acct.username}')
            # Prompt user to select an account
            user_idx = click.prompt(
                '\nEnter account number',
                type=click.Choice(range(len(all_accounts))),
                show_choices=False,
                default=0
            )
            # Use the selected account
            account = all_accounts[user_idx]
        # Returns the account or none
        return account

    def login_user(self):
        """Login with Fan Cult credentials."""
        account = self._get_account()
        if not account:
            return None

        # Make the login request
        success = self._make_login_request(
            account.username,
            self.manager.decode(account.password)
        )
        if not success:
            return None

        # Return the logged in account
        return account

    def _make_login_request(self, username, password):
        """Make a login request with the given credentials"""
        res = self.session.get(self.login_url)

        # Parse login form
        soup = BeautifulSoup(res.text, 'html.parser')
        login_form = soup.find('form')
        login_url = self.base_url + login_form.get('action')

        # Make login request
        res = self.session.post(login_url, data={
            'Username': username,
            'Password': password,
            'RememberMe': 'true'
        }, headers=self.headers)

        # Check login request result
        try:
            res.raise_for_status()
        except RequestException as ex:
            self.manager.error(f'Unable to login: {str(ex)}')
            return False

        # Check login status
        if not res.json()['LoginStatus']:
            self.manager.error('Unable to login: invalid credentials')
            return False

        # Return success
        return True

    def _get_rss_feed_generator(self, podcast=False):
        """Create a RSS feed generator object."""
        fg = FeedGenerator()
        fg.title(f'MFM Fan Cult {self.model_name.capitalize()}')
        fg.subtitle(f'Generated feed of Fan Cult exclusive {self.model_name}.')
        fg.author(self.copyright)
        fg.copyright(f"{datetime.now().year} {self.copyright['name']}")
        fg.logo(self.logo)
        fg.link(href=self.base_url, rel='alternate')
        fg.language('en')
        # Add additional info for podcasts
        if podcast:
            fg.load_extension('podcast')
            fg.podcast.itunes_author(self.copyright['name'])
            fg.podcast.itunes_owner(**self.copyright)
            fg.podcast.itunes_image(self.logo)
        return fg

    def _get_download_dir(self, dest, account, with_model=True):
        """Get and validate download directory."""
        dest_dir = dest if dest else account.download_dir
        # Append the model name
        if with_model:
            dest_dir = os.path.join(dest_dir, self.model_name.capitalize())
        # Check that download path exists
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir)
        return dest_dir

    def _get_download_path(self, base_path, file_name, yes):
        """Get and validate download file path."""
        file_path = os.path.join(base_path, file_name)

        # Check if episode file already exists
        if os.path.isfile(file_path):
            self.manager.warning(f'File "{file_path}" already exists')
            return None

        # Confirm the download
        if not yes:
            if not click.confirm(f'Download file to {file_path}?'):
                return None
        else:
            click.echo(f'Downloading file to {file_path}')
        return file_path

    @staticmethod
    def table(metadata):
        """Account database table definition."""
        return Table(
            'account',
            metadata,
            Column('username', EmailType, primary_key=True, unique=True),
            Column('password', BLOB, nullable=False),
            Column('download_dir', String, nullable=True),
            Column('last_updated', DateTime, server_default=func.now(),
                   onupdate=func.now(), nullable=False)
        )

    @property
    def login(self):
        """Command to login user."""
        @click.command(help='Login with your Fan Cult credentials.')
        @click.option('-u', '--username', prompt='Username')
        @click.password_option('-p', '--password')
        def fn(username, password):
            """Login with your Fan Cult credentials."""
            account = self.db.query(self.model) \
                .filter_by(username=username) \
                .first()
            # Add account if it is not found
            if not account:
                # Attempt to login
                success = self._make_login_request(username, password)
                # Save the account if successful
                if success:
                    account = self.model(
                        username=username,
                        password=self.manager.encode(password),
                        download_dir=self.manager.user_path
                    )
                    self.db.add(account)
                    self.db.commit()
                    self.manager.success('Successfully logged in!')
                return
            # Attempt to login
            success = self._make_login_request(username, password)
            # If the account was found, confirm password change
            if success:
                if click.confirm('Confirm password change for account'):
                    account.password = self.manager.encode(password)
                    self.db.commit()
                    self.manager.success('Successfully updated password!')
        return fn

    @property
    def update(self):
        """Command to update account info."""
        @click.command(help='Update account information.')
        @click.option('--download_dir', type=click.Path(exists=True),
                      help='Set path where files will be downloaded.')
        @login_user(self, with_account=True)
        def fn(download_dir, account):
            """Update account information."""
            if not download_dir:
                click.echo(click.get_current_context().get_help())
                return
            # Update the download directory in the database
            account.download_dir = download_dir
            self.db.commit()
            self.manager.success(f'Download path set to: {download_dir}')
        return fn

    @property
    def show(self):
        """Command to show account info."""
        @click.command(help='Display account information.')
        @login_user(self, with_account=True)
        def fn(account):
            """Display account information."""
            form = u'{0:>15}: {1}'
            account_data = '\n'.join([
                form.format('Username', account.username),
                form.format('Password', '*********** [hidden for security]'),
                form.format('Download Path', account.download_dir)
            ])
            click.echo(account_data)
        return fn

    @property
    def cli(self):
        """Command grouping for content actions."""
        @click.group()
        def fn():
            """Base group function for creating the CLI."""
            return
        # Set the description
        fn.help = self.command_help
        # Add all account commands
        for cmd in self.commands:
            fn.add_command(getattr(self, cmd), cmd)
        return fn
