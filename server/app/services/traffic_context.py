"""Display/journal correlation only; never an input to an ML model."""
import uuid

RUN_ID = uuid.uuid4().hex

def traffic_scope(feed):
    replay = feed.get('replay') or {}
    return ':'.join(map(str, (feed.get('source','none'), replay.get('session',''),
                             str(feed.get('dataTimeUtc') or 'no-time')[:10],
                             f"cycle{replay.get('cycle',0)}")))

def display_context(feed):
    return {'scope':traffic_scope(feed), 'runId':RUN_ID,
            'source':feed.get('source'), 'dataTimeUtc':feed.get('dataTimeUtc')}
