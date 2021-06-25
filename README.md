# mfm-fan-cult-manager

A CLI tool for viewing and downloading MFM Fan Cult exclusive content.

---
### Installation

Clone the repo and install using the setup.py file.

```
$ python setup.py install
```

### Usage

Access the manager using the `mfm-fan-cult` command.

```
$ mfm-fan-cult
Usage: mfm-fan-cult [OPTIONS] COMMAND [ARGS]...

  Manage Fan Cult exclusive content.

Options:
  --help  Show this message and exit.

Commands:
  account    Manage your Fan Cult account.
  minisodes  Manage Fan Cult exclusive minisodes.
  videos     Manage Fan Cult exclusive videos.
```


### Setup

Login to your MFM Fan Cult account before using the manager the first time.

```
$ mfm-fan-cult account login
Username: example@email.com
Password:
Repeat for confirmation:
Successfully logged in!
```

You'll need to run the update command for each content type to populate the database, for example:

```
$ mfm-fan-cult minisodes update
Scanning for new minisodes: 100%|███████████████████████████████████████████████| 10/10 minisodes
Added 10 new minisode(s)!
```

### List Content

Display a list of all content by type.

```
$ mfm-fan-cult minisodes list
+------+---------------+----------------------+----------------------------------------------------+-------------------------------------------------+
|   ID | Title         | Description          | Date                                               | URL                                             |
|------+---------------+----------------------+----------------------------------------------------+-------------------------------------------------|
|    1 | 09 June 2021  | Mini Minisode #10    | In Mini Minisode 10, Karen and Georgia do [...]    | https://myfavoritemurder.com/mini-minisode-10/  |
|    2 | 02 June 2021  | Mini Minisode #9     | In Mini Minisode 9, Karen and Georgia do two [...] | https://myfavoritemurder.com/mini-minisode-9/   |
|    3 | 26 May 2021   | Mini Minisode #8     | Welcome to Mini Minisode 8, in which Karen [...]   | https://myfavoritemurder.com/mini-minisode-8/   |
|    4 | 19 May 2021   | Mini Minisode #7     | In a new series, exclusively for members of [...]  | https://myfavoritemurder.com/mini-minisode-7/   |
|    5 | 12 May 2021   | Mini Minisode #6     | Welcome to Mini Minisode 6, in which Karen [...]   | https://myfavoritemurder.com/mini-minisode-6/   |
|    6 | 05 May 2021   | Mini Minisode #5     | Welcome to Mini Minisode 5, in which Karen [...]   | https://myfavoritemurder.com/mini-minisode-5/   |
|    7 | 28 April 2021 | Mini Minisode #4     | In a new series, exclusively for members of [...]  | https://myfavoritemurder.com/mini-minisode-4/   |
|    8 | 21 April 2021 | Mini Minisode #3     | In a new series, exclusively for members of [...]  | https://myfavoritemurder.com/mini-minisode-3/   |
|    9 | 14 April 2021 | Mini Minisode #2     | In a new series, exclusively for members of [...]  | https://myfavoritemurder.com/mini-minisode-002/ |
|   10 | 07 April 2021 | MFM Mini-Minisode #1 | For your ears only, Karen and Georgia are [...]    | https://myfavoritemurder.com/mini-minisode-001/ |
+------+---------------+----------------------+----------------------------------------------------+-------------------------------------------------+
```

### Show Content Info

Display info about a specific piece of content.

```
$ mfm-fan-cult minisodes show 1
             ID: 1
           Date: 09 June 2021
          Title: Mini Minisode #10
    Description: In Mini Minisode 10, Karen and Georgia do two extra hometown stories, pulled exclusively from the
                 Fan Cult forum. In this episode, they share the stories of a terrible doctor who
                 was not to be trusted and a mysterious vibration.
      Thumbnail: https://mfm-ms-central.azureedge.net/img/logo.jpg
          Audio: https://mfm-ms-central.azureedge.net/media/nnpbv5f1/mfm-mini-minisode-010_v1.mp3
            URL: https://myfavoritemurder.com/mini-minisode-10/
```

### Download Content

Download a file to your local drive.

```
$ mfm-fan-cult minisodes download 1
Download file to /Users/username/Minisodes/mfm-mini-minisode-010_v1.mp3? [y/N]: y
mfm-mini-minisode-010_v1.mp3: 100%|██████████████████████████████████████████| 13962/13962 [00:01<00:00, 11986.97KB/s]
```

By default files will be downloaded to user's home directory, but you can change the default destination for your account.

```
$ mfm-fan-cult account update --download_dir /path/to/destination
```

Or set the destination on a per-download basis:

```
$ mfm-fan-cult minisodes download 1 --dest /path/to/destinaton
```

### Open Content Link

Use the open command to launch the original content page on the MFM website in a browser.

```
$ mfm-fan-cult minisode open 1
Opening https://myfavoritemurder.com/mini-minisode-10/
```

### Help

You can always view the options for commands using the `--help` flag.

```
$ mfm-fan-cult minisodes --help
Usage: mfm-fan-cult minisodes [OPTIONS] COMMAND [ARGS]...

  Manage Fan Cult exclusive minisodes.

Options:
  --help  Show this message and exit.

Commands:
  download  Download a minisode by ID.
  list      Show all available mini-minisodes.
  open      Open web page for minisode.
  show      Show minisode details by ID.
  update    Updates the the list of minisodes.
```
