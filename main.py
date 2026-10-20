from dify_plugin import DifyPluginEnv, Plugin

# Create Videos may wait up to 90 seconds for a web page to be analysed, so the
# request timeout leaves room for that plus the API calls around it.
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=180))

if __name__ == "__main__":
    plugin.run()
