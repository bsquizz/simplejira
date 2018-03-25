This file is used to track project TODO's

* editing other details of a card (e.g. title, description -- via prompt if short, otherwise the text editor would be opened if desired -- the jiraprompt.common.editor_ignore_comments() method can be used here as it is in other areas)
* editing entire card ~~and entire worklog~~ (only for the details we care about, via opening an editor)
    - this requires the 'updater' process on ResourceCollection class to be fully built out (maybe? didn't use this approach for worklogs.)
    - the idea is the fields from the collection are converted to yaml (see ResourceCollection.convert_to_yaml()), the editor is opened to allow
      the user to edit that YAML, and when the file is saved the client will update the issue on the server-side by translating the YAML back
      into the needed params/fields
* the client needs to intelligently refresh so you can leave it open a long time -- e.g. refresh auth, and detect changes if you run it overnight like the active sprint changing -- need to find the max reasonable time between running a refresh and possible keep a background 'refresher' thread going in the JiraWrapper class -- right now this can manually be done using the 'reload' cmd in the main prompt
* write a real README
