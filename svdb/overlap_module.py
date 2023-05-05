from __future__ import absolute_import

# check the "overlap" of interchromosomaltranslocations


def precise_overlap(chrApos_query, chrBpos_query, chrApos_db, chrBpos_db, distance):
    Adist = abs(chrApos_query - chrApos_db)
    Bdist = abs(chrBpos_query - chrBpos_db)
    if max([Adist, Bdist]) <= distance:
        return max([Adist, Bdist]), True
    return False, False

# check if intrachromosomal vaiants overlap


# event is in the DB, variation is the new variation I want to insert
def isSameVariation(chrApos_query, chrBpos_query, chrApos_db, chrBpos_db, ratio, distance):
    if abs(chrApos_query - chrApos_db) <= distance and abs(chrBpos_query - chrBpos_db) <= distance:
        return 1, True
    else:
        return None, False


def variant_overlap(chrA, chrB, chrApos_query, chrBpos_query, chrApos_db, chrBpos_db, ratio, distance):
    match = False
    overlap = False
    if chrA == chrB:
        overlap, match = isSameVariation(
            chrApos_query, chrBpos_query, chrApos_db, chrBpos_db, ratio, distance)
    else:
        overlap, match = precise_overlap(
            chrApos_query, chrBpos_query, chrApos_db, chrBpos_db, distance)
    return overlap, match
