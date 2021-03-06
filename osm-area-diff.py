#!/usr/bin/python
# vim: set fileencoding=UTF-8

# Copyright 2018 L. David Baron <dbaron@dbaron.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import imp
import os
import os.path
import sys
from datetime import datetime
from optparse import OptionParser

# git clone git@github.com:metaodi/osmapi.git
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "osmapi"))
import osmapi

op = OptionParser()
(options, args) = op.parse_args()

if len(args) != 6:
    op.error("expected six arguments (min_lon, min_lat, max_lon, max_lat, start_time, end_time) but got {0}".format(len(args)))

passwords = imp.load_source("passwords", "/home/dbaron/.passwords.py")

api = osmapi.OsmApi(username=passwords.get_osm_username(), password=passwords.get_osm_password())

min_lon = float(args[0])
min_lat = float(args[1])
max_lon = float(args[2])
max_lat = float(args[3])
os.environ["TZ"] = "UTC"
start_time = datetime.utcfromtimestamp(int(args[4]))
end_time = datetime.utcfromtimestamp(int(args[5]))

changed_objects = {
    "node": {},
    "way": {},
    "relation": {}
}

search_area = (max_lon - min_lon) * (max_lat - min_lat)

search_start = start_time
search_end = end_time

while True:
    # https://wiki.openstreetmap.org/wiki/API_v0.6#Query:_GET_.2Fapi.2F0.6.2Fchangesets
    changesets = api.ChangesetsGet(min_lon = min_lon, min_lat = min_lat,
                                   max_lon = max_lon, max_lat = max_lat,
                                   closed_after = search_start.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                                   created_before = search_end.strftime("%Y-%m-%dT%H:%M:%S+00:00"))

    closed_min = None
    closed_max = None
    created_min = None
    created_max = None

    for changeset_id in changesets:
        changeset_meta = api.ChangesetGet(changeset_id)
        if closed_min is None or changeset_meta["closed_at"] < closed_min:
            closed_min = changeset_meta["closed_at"]
        if closed_max is None or changeset_meta["closed_at"] > closed_max:
            closed_max = changeset_meta["closed_at"]
        if created_min is None or changeset_meta["created_at"] < created_min:
            created_min = changeset_meta["created_at"]
        if created_max is None or changeset_meta["created_at"] > created_max:
            created_max = changeset_meta["created_at"]
        changeset_area = (float(changeset_meta["max_lon"]) - float(changeset_meta["min_lon"])) * (float(changeset_meta["max_lat"]) - float(changeset_meta["min_lat"]))
        area_ratio = changeset_area / search_area
        sys.stderr.write("Downloading changeset {0} (area ratio {1})... ".format(changeset_id, area_ratio))
        changeset = api.ChangesetDownload(changeset_id)
        # FIXME: Add --exclude option instead of hardcoding.
        count = len(changeset)
        sys.stderr.write("(count {0}) ".format(count))
        if area_ratio > 1000 and count > 30:
            sys.stderr.write("Skipping!\n".format(changeset_id, area_ratio))
            continue
        sys.stderr.write("\n")
        for change in changeset:
            t = change["type"]
            i = change["data"]["id"]
            changed_objects[t][i] = True

    if len(changesets) < 100:
        sys.stderr.write("Search produced {0} changesets, stopping.\n".format(len(changesets)))
        break
    # We were limited to 100 changesets, so fiddle with the times to get more.
    sys.stderr.write("Search  {0} to {1}\n".format(search_start, search_end))
    sys.stderr.write("Created {0} to {1}\n".format(created_min, created_max))
    sys.stderr.write("Closed  {0} to {1}\n".format(closed_min, closed_max))
    sys.stderr.write("Doing revised search.\n")
    search_end = closed_min

for node_id in changed_objects["node"]:
    sys.stderr.write("Downloading node {0}.\n".format(node_id))
    h = api.NodeHistory(node_id)
    start_version = None
    end_version = None
    for version in h:
        v = h[version]
        t = v["timestamp"]
        if t < start_time:
            start_version = v # overwrites repeatedly
        if t < end_time:
            end_version = v # overwrites repeatedly
    if start_version is None:
        if end_version["visible"]:
            print "Presence: node {0} added.".format(node_id)
        continue
    if start_version["visible"] != end_version["visible"]:
        print "Presence: node {0} {1}.".format(node_id, "removed" if start_version["visible"] else "re-added")
        continue
    if start_version["lon"] != end_version["lon"]:
        print "Lon on node {2} changed from {0} to {1}".format(start_version["lon"], end_version["lon"], node_id)
    if start_version["lat"] != end_version["lat"]:
        print "Lat on node {2} changed from {0} to {1}".format(start_version["lat"], end_version["lat"], node_id)
    if start_version["tag"] != end_version["tag"]:
        print "Tags on node {2} changed from {0} to {1}".format(start_version["tag"], end_version["tag"], node_id)

for way_id in changed_objects["way"]:
    sys.stderr.write("Downloading way {0}.\n".format(way_id))
    h = api.WayHistory(way_id)
    start_version = None
    end_version = None
    for version in h:
        v = h[version]
        t = v["timestamp"]
        if t < start_time:
            start_version = v # overwrites repeatedly
        if t < end_time:
            end_version = v # overwrites repeatedly
    if start_version is None:
        if end_version["visible"]:
            print "Presence: way {0} added.".format(way_id)
        continue
    if start_version["visible"] != end_version["visible"]:
        print "Presence: way {0} {1}.".format(way_id, "removed" if start_version["visible"] else "re-added")
        continue
    if start_version["nd"] != end_version["nd"]:
        print "Nodes on way {2} changed from {0} to {1}".format(start_version["nd"], end_version["nd"], way_id)
    if start_version["tag"] != end_version["tag"]:
        print "Tags on way {2} changed from {0} to {1}".format(start_version["tag"], end_version["tag"], way_id)

for relation_id in changed_objects["relation"]:
    sys.stderr.write("Downloading relation {0}.\n".format(relation_id))
    h = api.RelationHistory(relation_id)
    start_version = None
    end_version = None
    for version in h:
        v = h[version]
        t = v["timestamp"]
        if t < start_time:
            start_version = v # overwrites repeatedly
        if t < end_time:
            end_version = v # overwrites repeatedly
    if start_version is None:
        if end_version["visible"]:
            print "Presence: relation {0} added.".format(relation_id)
        continue
    if start_version["visible"] != end_version["visible"]:
        print "Presence: relation {0} {1}.".format(relation_id, "removed" if start_version["visible"] else "re-added")
        continue
    if start_version["member"] != end_version["member"]:
        print "Members on relation {2} changed from {0} to {1}".format(start_version["member"], end_version["member"], relation_id)
    if start_version["tag"] != end_version["tag"]:
        print "Tags on relation {2} changed from {0} to {1}".format(start_version["tag"], end_version["tag"], relation_id)
