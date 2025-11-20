from notifier.email import send_markdown_email_from_file


if __name__ == "__main__":
    send_markdown_email_from_file(
        markdown_path="tasks/sunday-movies/data/showtimes.md",
        subject="Sunday Movies Showtimes",
        to_addresses=["hou.d.xinli@gmail.com"],
    )
