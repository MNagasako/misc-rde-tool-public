# config/site_rde.py
URL_RDE_BASE = "https://rde.nims.go.jp/"
URL_RDE_BASE_WITUOUT_SLASH = "https://rde.nims.go.jp"
URL_RDE_API_BASE = "https://rde-api.nims.go.jp/"
URL_RDE_API_BASE_WITUOUT_SLASH = "https://rde-api.nims.go.jp"

URLS = {
    "web": {
        "domain": f"{URL_RDE_BASE_WITUOUT_SLASH}",
        "base": f"{URL_RDE_BASE}",
        "login": f"{URL_RDE_BASE}",
        "logout": f"{URL_RDE_BASE}logout",
        "dataset_page": f"{URL_RDE_BASE}rde/datasets/{{id}}",
        "data_detail_page": f"{URL_RDE_BASE}rde/datasets/data/{{id}}"
    },
    "api": {
        "domain": f"{URL_RDE_API_BASE_WITUOUT_SLASH}",
        "search": f"{URL_RDE_API_BASE}datasets?sort=-modified&page%5Boffset%5D=0&page%5Blimit%5D=30&filter%5BgrantNumber%5D={{id}}&include=manager%2Creleases&fields%5Buser%5D=id%2CuserName%2CorganizationName%2CisDeleted&fields%5Brelease%5D=version%2CreleaseNumber",
        "dataset_detail": f"{URL_RDE_API_BASE}datasets/{{id}}?updateViews=true&include=releases%2Capplicant%2Cprogram%2Cmanager%2CrelatedDatasets%2Ctemplate%2Cinstruments%2Clicense%2CsharingGroups&fields%5Brelease%5D=id%2CreleaseNumber%2Cversion%2Cdoi%2Cnote%2CreleaseTime&fields%5Buser%5D=id%2CuserName%2CorganizationName%2CisDeleted&fields%5Bgroup%5D=id%2Cname&fields%5BdatasetTemplate%5D=id%2CnameJa%2CnameEn%2Cversion%2CdatasetType%2CisPrivate%2CworkflowEnabled&fields%5Binstrument%5D=id%2CnameJa%2CnameEn%2Cstatus&fields%5Blicense%5D=id%2Curl%2CfullName",
        "data": f"{URL_RDE_API_BASE}data?filter%5Bdataset.id%5D={{id}}&sort=-created&page%5Boffset%5D=0&page%5Blimit%5D=24&include=owner%2Csample%2CthumbnailFile%2Cfiles",
        "data_files": f"{URL_RDE_API_BASE}data/{{id}}/files?page%5Blimit%5D=100&page%5Boffset%5D=0&filter%5BfileType%5D%5B%5D=META&filter%5BfileType%5D%5B%5D=MAIN_IMAGE&filter%5BfileType%5D%5B%5D=OTHER_IMAGE&filter%5BfileType%5D%5B%5D=NONSHARED_RAW&filter%5BfileType%5D%5B%5D=RAW&filter%5BfileType%5D%5B%5D=STRUCTURED&fileTypeOrder=RAW%2CNONSHARED_RAW%2CMETA%2CSTRUCTURED%2CMAIN_IMAGE%2COTHER_IMAGE",
        "data_detail": f"{URL_RDE_API_BASE}data/{{id}}?updateViews=true&include=releases%2Cinvoice%2Cowner%2Cinstrument%2Cfiles%2CthumbnailFile%2Cdataset&fields%5Brelease%5D=id%2CreleaseNumber%2Cversion&fields%5Buser%5D=id%2CuserName%2CisDeleted&fields%5Binstrument%5D=id%2CnameJa%2CnameEn%2Cstatus"
    }
}
