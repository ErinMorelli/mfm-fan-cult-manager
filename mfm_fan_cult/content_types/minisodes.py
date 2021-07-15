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
import re
from math import ceil
from textwrap import shorten, TextWrapper

import pytz
import click
from tqdm import tqdm
from dateutil import parser
from bs4 import BeautifulSoup
from tabulate import tabulate, tabulate_formats

from sqlalchemy.sql import or_
from sqlalchemy import Table, Column, DateTime, Integer, String, func
from sqlalchemy_utils.types import URLType

from mfm_fan_cult.content import FanCultContent


class MinisodeContent(FanCultContent):
    """Manage Fan Cult minisode content."""
    command = 'minisodes'
    model_name = command
    # Minisode-specific URL for HTTP requests
    episodes_url = f'{FanCultContent.base_url}/episodes'
    # Download chunk size
    chunk_size = 1024
    # Set CLI details for minisodes
    command_help = 'Manage Fan Cult exclusive minisodes.'
    commands = ['list', 'update', 'show', 'download', 'open', 'feed']

    def _update_episodes(self):
        """Add new episodes to database."""
        res = self.session.get(self.episodes_url)
        soup = BeautifulSoup(res.text, 'html.parser')

        # Get only fan cult episodes
        all_eps = soup.find('div', class_='eps')
        fan_cult_eps = all_eps.find_all('div', class_='fancult-tag')

        #  Set up progress bar data
        progress_bar = {
            'iterable': fan_cult_eps,
            'unit': 'minisodes',
            'desc': 'Scanning for new minisodes',
            'bar_format': '{l_bar}{bar}| {n_fmt}/{total_fmt} {unit}'
        }

        # Parse list of episodes
        added = []
        for fan_cult_ep in tqdm(**progress_bar):
            episode = self._create_episode(fan_cult_ep.parent.parent)
            if episode:
                added.append(episode)
                self.db.add(episode)

        # Commit the session, if needed
        if added:
            self.db.commit()

        # Return the list of added episodes
        return added

    def _create_episode(self, ep):
        """Creates a new episode database entry."""
        ep_url = self.base_url + ep.a['href'].strip()
        ep_title = ep.h1.text.strip()

        # Check for existing
        if self._find_episode(ep_title, ep_url):
            return None

        # Get episode page content
        res = self.session.get(ep_url)
        soup = BeautifulSoup(res.text, 'html.parser')

        # Parse episode page
        about = soup.find('div', class_='home-about')
        script = soup.find_all('script', src='')[1]

        # Return the new episode object
        return self.model(
            title=ep_title,
            description=about.p.text.strip(),
            date=self._get_episode_date(ep),
            url=ep_url,
            image=about.img['src'].strip(),
            audio=re.search(r'm4a: "(.+)"', str(script)).group(1).strip()
        )

    def _find_episode(self, title, url):
        """Search for episode in the database by title and URL."""
        return self.db.query(self.model)\
            .filter_by(title=title, url=url)\
            .one_or_none()

    def _download_episode(self, episode, episode_path, yes):
        """Downloads an audio file to the specified path."""
        file_name = os.path.basename(episode.audio)
        file_path = self._get_download_path(episode_path, file_name, yes)
        if not file_path:
            return

        # Get the file stream data
        stream = self.session.get(episode.audio, stream=True)
        total_length = int(stream.headers.get('content-length', 0))

        # Set up progress bar data
        progress_bar = {
            'iterable': stream.iter_content(chunk_size=self.chunk_size),
            'total': int(ceil(total_length / float(self.chunk_size))),
            'unit': 'KB',
            'desc': file_name
        }

        # Download the file and display progress
        with open(file_path, "wb") as f:
            for chunk in tqdm(**progress_bar):
                if chunk:
                    f.write(chunk)
                    f.flush()

        # Check that the file was downloaded
        if not os.path.isfile(file_path):
            self.manager.error(f'Problem downloading file: {file_path}')

    @staticmethod
    def _get_episode_date(ep):
        """Parse the episode date into a datetime object."""
        date_div = ep.find('div', class_='ep-date')
        date_dd = date_div.h3.text.strip()
        date_mm_yy = date_div.h4.text.strip()
        return parser.parse(f'{date_dd} {date_mm_yy}')

    def _create_episode_feed(self, file_dir, print_=False):
        """Create a RSS feed from stored episode data."""
        file_path = os.path.join(file_dir, f'{self.model_name}.xml')

        # Get the feed generator object
        fg = self._get_rss_feed_generator(podcast=True)

        # Get all minisodes
        episodes = self.db.query(self.model) \
            .order_by(self.model.date.asc()) \
            .all()

        # Create entries for episodes
        for episode in episodes:
            # Get audio file details
            res = self.session.head(episode.audio)
            audio_type = res.headers.get('Content-Type')
            audio_length = res.headers.get('Content-Length')

            # Create the RSS entry
            fe = fg.add_entry()
            fe.id(str(episode.minisode_id))
            fe.title(episode.title)
            fe.description(episode.description)
            fe.published(pytz.utc.localize(episode.date))
            fe.link(href=episode.url)
            fe.podcast.itunes_author('Exactly Right')
            fe.podcast.itunes_image(episode.image)
            fe.enclosure(episode.audio, audio_length, audio_type)

        # Print the XML
        if print_:
            click.echo(fg.rss_str(pretty=True).decode('utf-8'))
            return

        # Save the XML to a file
        fg.rss_file(file_path, pretty=True)
        self.manager.success(f'RSS file created: {file_path}')

    @staticmethod
    def table(metadata):
        """Minisode database table definition."""
        return Table(
            'minisodes',
            metadata,
            Column('minisode_id', Integer, primary_key=True),
            Column('title', String, nullable=False),
            Column('description', String, nullable=False),
            Column('date', DateTime, nullable=False),
            Column('url', URLType, nullable=False),
            Column('image', URLType, nullable=False),
            Column('audio', URLType, nullable=False),
            Column('last_updated', DateTime, server_default=func.now(),
                   onupdate=func.now(), nullable=False),
        )

    @staticmethod
    def format_episode_list(episodes, fmt='psql'):
        """Create a formatted list of episodes."""
        fields = ['ID', 'Title', 'Description', 'Date', 'URL']
        table_data = [[
            episode.minisode_id,
            episode.date.strftime('%d %B %Y'),
            episode.title,
            shorten(episode.description, width=50),
            shorten(episode.url, width=50)
        ] for episode in episodes]
        return tabulate(table_data, fields, tablefmt=fmt)

    def get_episode(self, episode_id):
        """Get minisode in database by ID."""
        episode = self.db.query(self.model).get(episode_id)
        if not episode:
            self.manager.error(f'No minisode found for ID: {episode_id}')
            return None
        return episode

    @property
    def update(self):
        """Command to update the database with new minisodes"""
        @click.command(help='Updates the the list of minisodes.')
        @click.option('-l', '--list', 'list_', is_flag=True,
                      help='List any newly added minisodes')
        @self.auto_login_user()
        def fn(list_):
            """Updates the the list of minisodes."""
            new_episodes = self._update_episodes()
            # Check for results
            if not new_episodes:
                self.manager.info('No new minisodes found.')
                return
            # Print out new episodes
            self.manager.success(f'Added {len(new_episodes)} new minisode(s)!')
            if list_:
                click.echo(self.format_episode_list(new_episodes))
        return fn

    @property
    def download(self):
        """Command to download a given episode"""
        @click.command(help='Download a minisode by ID.')
        @click.option('-y', '--yes', is_flag=True,
                      help='Download without confirmation.')
        @click.option('-d', '--dest', type=click.Path(exists=True),
                      help='Folder to download file to.')
        @click.argument('minisode_id')
        @self.auto_login_user(with_account=True)
        def fn(minisode_id, yes, dest, account):
            """Download a minisode by ID."""
            episode_path = self._get_download_dir(dest, account)
            episode = self.get_episode(minisode_id)
            if episode:
                self._download_episode(episode, episode_path, yes)
        return fn

    @property
    def show(self):
        """Command to display minisode details."""
        @click.command(help='Show minisode details by ID.')
        @click.argument('minisode_id')
        @self.auto_login_user()
        def fn(minisode_id):
            """Show minisode details by ID."""
            episode = self.get_episode(minisode_id)
            if episode:
                form = u'{0:>15}: {1}'
                wrapper = TextWrapper(width=100,
                                      initial_indent='',
                                      subsequent_indent='                 ')
                description = '\n'.join(wrapper.wrap(episode.description))
                episode_data = '\n'.join([
                    form.format('ID', episode.minisode_id),
                    form.format('Date', episode.date.strftime('%d %B %Y')),
                    form.format('Title', episode.title),
                    form.format('Description', description),
                    form.format('Thumbnail', episode.image),
                    form.format('Audio', episode.audio),
                    form.format('URL', episode.url),
                ])
                click.echo(episode_data)
        return fn

    @property
    def open(self):
        """Command to open minisode link in a browser."""
        @click.command(help='Open web page for minisode.')
        @click.argument('minisode_id')
        @self.auto_login_user()
        def fn(minisode_id):
            """Open web page for minisode."""
            episode = self.get_episode(minisode_id)
            if episode:
                click.echo(f'Opening {episode.url}')
                click.launch(episode.url)
        return fn

    @property
    def list(self):
        """Command to display a list of minisodes."""
        @click.command(help='Show all available minisodes.')
        @click.option('-n', '--number', default=10, show_default=True,
                      help='Number of minisodes to get.')
        @click.option('-r', '--refresh', is_flag=True,
                      help='Update list of minisodes.')
        @click.option('-f', '--format', 'fmt', default='psql',
                      type=click.Choice(tabulate_formats), show_choices=False,
                      show_default=True, help='How to format the list.')
        @click.option('-s', '--search',
                      help='Search minisodes by title and description.')
        @self.auto_login_user()
        def fn(number, refresh, fmt, search):
            """Show all available minisodes."""
            if refresh:
                self._update_episodes()
            # Set up query
            query = self.db.query(self.model)\
                .order_by(self.model.date.desc())
            # Handle search query
            if search:
                query = query.filter(or_(
                    self.model.title.like(f'%{search}%'),
                    self.model.description.like(f'%{search}%')
                ))
            # Handle limit
            if number > 0:
                query = query.limit(number)
            # Run the query
            episodes = query.all()
            if not episodes:
                self.manager.warning('No minisodes found.')
                return
            # Display the list
            click.echo(self.format_episode_list(episodes, fmt=fmt))
        return fn

    @property
    def feed(self):
        """Command to generate RSS feed."""
        @click.command(help='Generate a RSS feed of available minisodes.')
        @click.option('-p', '--print', 'print_', is_flag=True,
                      help='Print XML without saving to file')
        @click.option('-d', '--dest', type=click.Path(exists=True),
                      help='Folder to download file to.')
        @click.option('-r', '--refresh', is_flag=True,
                      help='Update list of minisodes.')
        @self.auto_login_user(with_account=True)
        def fn(print_, dest, refresh, account):
            """Generate a RSS feed of available minisodes."""
            if refresh:
                self._update_episodes()
            # Generate feed
            path = self._get_download_dir(dest, account, with_model=False)
            self._create_episode_feed(path, print_)
        return fn
