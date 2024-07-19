# README

Parse slack history exported from [Backupery](https://www.backupery.com/) and generate pdf.

With the free version of Backupery, message history of slack is exported, but no readable files generated. If you export the slack history on Windows, you can get files including

- `HTML2`: partial message history
- `ReadyToImport`: including a zip file that contains raw history
    
Unzip the file to a directory, and run `parse.py` from this repo. E.g., `./backupery_slack_parser/parse.py ./[unzip path]` exported all history.

`./backupery_slack_parser/parse.py ./[unzip path] --filter [filter-file]` exports only messages of selected chats on selected dates. See `filter.yaml` for example.

You should see pdf files generated based on the raw history.

献给阿尔弗雷德
