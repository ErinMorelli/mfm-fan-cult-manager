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
from dateutil import parser
from textwrap import shorten
from urllib.parse import quote

import pytz
import click
from tqdm import tqdm
from bs4 import BeautifulSoup
from vimeo_downloader import Vimeo
from tabulate import tabulate, tabulate_formats

from sqlalchemy_utils.types import URLType
from sqlalchemy import Table, Column, DateTime, Integer, String, func

from mfm_fan_cult.content import FanCultContent

from . import login_user


class VideoContent(FanCultContent):
    """Manage Fan Cult video content."""
    command = 'videos'
    model_name = command
    # Video-specific URLs for HTTP requests
    news_url = f'{FanCultContent.base_url}/umbraco/Surface/NewsSurface/GetNews'
    vimeo_url = 'https://vimeo.com/api/oembed.json?url='
    # Thumbnail generator URL
    vimeo_thumbnail = 'https://i.vimeocdn.com/filter/overlay?src0={src}' \
                      'src1=http%3A%2F%2Ff.vimeocdn.com%2Fp%2Fimages%2Fcrawler_play.png'
    # Set CLI details for videos
    command_help = 'Manage Fan Cult exclusive videos.'
    commands = ['list', 'update', 'show', 'download', 'open', 'feed']

    def _update_videos(self, limit=100):
        """Add new video content to database."""
        res = self.session.post(self.news_url, params={
            'page': 0,
            'pagesize': limit,
            'articletype': 1,
            'onlyfancult': 'false'
        })

        # Parse news feed results
        soup = BeautifulSoup(res.text, 'html.parser')
        news = soup.find('div', class_='news-grid')
        all_articles = news.find_all('div', class_='')

        #  Set up progress bar data
        progress_bar = {
            'iterable': all_articles,
            'unit': 'videos',
            'desc': 'Scanning for new videos',
            'bar_format': '{l_bar}{bar}| {n_fmt}/{total_fmt} {unit}'
        }

        # Parse articles
        added = []
        for article in tqdm(**progress_bar):
            video = self._create_video(article)
            if video:
                added.append(video)
                self.db.add(video)

        # Only commit the changes if anything was added
        if added:
            self.db.commit()

        # Return the list of added videos
        return added

    def _find_video(self, title, url):
        """Searches for a video in the database by title and URL."""
        return self.db.query(self.model)\
            .filter_by(title=title, url=url)\
            .one_or_none()

    def _create_video(self, article):
        """Creates a new video entry in the database."""
        if not article.h1:
            return None

        # Parse the title and URL from the HTML
        video_title = article.h1.text.strip()
        video_url = self.base_url + article.a['href'].strip()

        # Exit if the video already exists
        if self._find_video(video_title, video_url):
            return None

        # Parse the date and video type
        date_str, video_type = article.h6.text.strip()[:-1].split(' - ')

        # Parse the vimeo URL
        vimeo_url = article.find('div', class_='bg-image')['data-vimeo']

        # Get file metadata
        video_metadata = self._get_video_metadata(vimeo_url)

        # Return the new video object
        return self.model(
            title=video_title,
            type=video_type,
            date=parser.parse(date_str),
            url=video_url,
            image=video_metadata['thumbnail_url'],
            video_image=video_metadata['thumbnail_url_with_play_button'],
            video=vimeo_url
        )

    def _get_video_metadata(self, video_url):
        """Retrieve video metadata from Vimeo."""
        vimeo_video_url = self.vimeo_url + video_url

        # Get video JSON metadata from Vimeo
        res = self.session.get(vimeo_video_url, headers=self.headers)
        return res.json()

    def _download_video(self, video, video_path, yes):
        """Downloads a video file to the specified path."""
        video_metadata = self._get_video_metadata(video.video)

        # Parse iframe for src URL
        soup = BeautifulSoup(video_metadata['html'], 'html.parser')
        video_src = soup.iframe['src'].strip().split('?')[0]

        # Creat a new Vimeo video object
        vimeo = Vimeo(video_src, embedded_on=video.url)

        # Select the best quality stream
        stream = vimeo.best_stream

        # Format the file name from the title
        file_name = stream.title
        if not file_name.endswith(".mp4"):
            file_name += ".mp4"

        # Check to see if the video already exists
        file_path = self._get_download_path(video_path, file_name, yes)
        if not file_path:
            return

        # Perform the download
        stream.download(download_directory=video_path)

        # Check that the file was downloaded
        if not os.path.isfile(file_path):
            self.manager.error(f'Problem downloading file: {file_path}')

    def _create_video_feed(self, file_dir, print_=False, limit=25):
        """Create a RSS feed from stored video data."""
        file_path = os.path.join(file_dir, f'{self.model_name}.xml')

        # Get the feed generator object
        fg = self._get_rss_feed_generator()
        fg.load_extension('media')

        # Get all videos
        videos = self.db.query(self.model) \
            .order_by(self.model.date.desc()) \
            .limit(limit)\
            .all()

        # Create entries for videos
        for video in videos:
            # Set up content
            content = f'<p>{video.type}</p>' \
                      f'<p><a href="{video.url}">' \
                      f'<img src="{video.video_image}"/>' \
                      f'</a></p>'
            # Set RSS entry details
            fe = fg.add_entry()
            fe.id(str(video.video_id))
            fe.title(video.title)
            fe.content(content, type='CDATA')
            fe.description(video.type)
            fe.published(pytz.utc.localize(video.date))
            fe.link(href=video.url)
            fe.author(self.copyright)
            fe.media.thumbnail({'url': video.image})
            fe.media.content({'url': video.video})

        # Print the XML
        if print_:
            click.echo(fg.rss_str(pretty=True).decode('utf-8'))
            return

        # Save the XML to a file
        fg.rss_file(file_path, pretty=True)
        self.manager.success(f'RSS file created: {file_path}')

    @staticmethod
    def table(metadata):
        """Video database table definition."""
        return Table(
            'videos',
            metadata,
            Column('video_id', Integer, primary_key=True),
            Column('title', String, nullable=False),
            Column('type', String, nullable=False),
            Column('date', DateTime, nullable=False),
            Column('url', URLType, nullable=False),
            Column('image', URLType, nullable=False),
            Column('video', URLType, nullable=False),
            Column('video_image', URLType, nullable=False),
            Column('last_updated', DateTime, server_default=func.now(),
                   onupdate=func.now(), nullable=False),
        )

    @staticmethod
    def format_video_list(videos, fmt='psql'):
        """Create a formatted list of videos."""
        fields = ['ID', 'Date', 'Title', 'Type', 'URL']
        table_data = [[
            video.video_id,
            video.date.strftime('%d %B %Y'),
            shorten(video.title, width=50),
            video.type,
            shorten(video.url, width=50)
        ] for video in videos]
        return tabulate(table_data, fields, tablefmt=fmt)

    def get_video(self, video_id):
        """Get video in database by ID."""
        video = self.db.query(self.model).get(video_id)
        if not video:
            self.manager.error(f'No video found for ID: {video_id}')
            return None
        return video

    @property
    def update(self):
        """Command to update the database with new videos."""
        @click.command(help='Updates the the list of videos.')
        @click.option('-l', '--list', 'list_', is_flag=True,
                      help='List any newly added minisodes')
        @click.option('-n', '--number', default=100, show_default=True,
                      help='Number of videos to retrieve from archive')
        @login_user(self)
        def fn(number, list_):
            """Updates the the list of videos."""
            new_videos = self._update_videos(number)
            # Check for results
            if not new_videos:
                self.manager.info('No new videos found.')
                return
            # Print list of newly added videos
            self.manager.success(f'Added {len(new_videos)} new video(s)!')
            if list_:
                click.echo(self.format_video_list(new_videos))
        return fn

    @property
    def download(self):
        """Command to download a given video."""
        @click.command(help='Download a video by ID.')
        @click.option('-y', '--yes', is_flag=True,
                      help='Download without confirmation.')
        @click.option('-d', '--dest', type=click.Path(exists=True),
                      help='Folder to download file to.')
        @click.argument('video_id')
        @login_user(self, with_account=True)
        def fn(video_id, yes, dest, account):
            """Download a video by ID."""
            video_path = self._get_download_dir(dest, account)
            video = self.get_video(video_id)
            if video:
                self._download_video(video, video_path, yes)
        return fn

    @property
    def show(self):
        """Command to display video details."""
        @click.command(help='Show video details by ID')
        @click.argument('video_id')
        @login_user(self)
        def fn(video_id):
            """Show video details by ID."""
            video = self.get_video(video_id)
            if video:
                form = u'{0:>15}: {1}'
                video_data = '\n'.join([
                    form.format('ID', video.video_id),
                    form.format('Date', video.date.strftime('%d %B %Y')),
                    form.format('Title', video.title),
                    form.format('Type', video.type),
                    form.format('Thumbnail', video.image),
                    form.format('Video', video.video),
                    form.format('URL', video.url)
                ])
                click.echo(video_data)
        return fn

    @property
    def open(self):
        """Command to open video link in a browser."""
        @click.command(help='Open web page for video.')
        @click.argument('video_id')
        @login_user(self)
        def fn(video_id):
            """Open web page for video."""
            video = self.get_video(video_id)
            if video:
                click.echo(f'Opening {video.url}')
                click.launch(video.url)
        return fn

    @property
    def list(self):
        """Command to display a list of videos."""
        @click.command(help='Show all available videos.')
        @click.option('-n', '--number', default=10, show_default=True,
                      help='Number of videos to get.')
        @click.option('-r', '--refresh', is_flag=True,
                      help='Update list of videos.')
        @click.option('-f', '--format', 'fmt', default='psql',
                      type=click.Choice(tabulate_formats), show_choices=False,
                      show_default=True, help='How to format the list.')
        @click.option('-t', '--type', 'type_',
                      help='Filter the list by video type.')
        @click.option('-s', '--search',
                      help='Search videos by title.')
        @login_user(self)
        def fn(number, refresh, fmt, type_=None, search=None):
            """Show all available videos."""
            if refresh:
                self._update_videos()
            # Set up query
            query = self.db.query(self.model) \
                .order_by(self.model.date.desc())
            # Handle type filtering
            if type_:
                query = query.filter(self.model.type.like(f'%{type_}%'))
            # Handle search query
            if search:
                query = query.filter(self.model.title.like(f'%{search}%'))
            # Handle limit
            if number > 0:
                query = query.limit(number)
            # Run the query
            videos = query.all()
            if not videos:
                self.manager.warning('No videos found.')
                return
            # Display the list
            click.echo(self.format_video_list(videos, fmt=fmt))
        return fn

    @property
    def feed(self):
        """Command to generate RSS feed."""
        @click.command(help='Generate a RSS feed of available videos.')
        @click.option('-n', '--number', default=10, show_default=True,
                      help='Number of videos to get for feed.')
        @click.option('-p', '--print', 'print_', is_flag=True,
                      help='Print XML without saving to file')
        @click.option('-d', '--dest', type=click.Path(exists=True),
                      help='Folder to download file to.')
        @click.option('-r', '--refresh', is_flag=True,
                      help='Update list of minisodes.')
        @login_user(self, with_account=True)
        def fn(number, print_, dest, refresh, account):
            """Generate a RSS feed of available videos."""
            if refresh:
                self._update_videos(limit=number)
            # Generate feed
            path = self._get_download_dir(dest, account, with_model=False)
            self._create_video_feed(path, print_, limit=number)
        return fn
