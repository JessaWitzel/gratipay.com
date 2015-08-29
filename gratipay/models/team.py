"""Teams on Gratipay are plural participants with members.
"""
from postgres.orm import Model


class Team(Model):
    """Represent a Gratipay team.
    """

    typname = 'teams'

    def __eq__(self, other):
        if not isinstance(other, Team):
            return False
        return self.id == other.id

    def __ne__(self, other):
        if not isinstance(other, Team):
            return True
        return self.id != other.id


    # Constructors
    # ============

    @classmethod
    def from_id(cls, id):
        """Return an existing team based on id.
        """
        return cls._from_thing("id", id)

    @classmethod
    def from_slug(cls, slug):
        """Return an existing team based on slug.
        """
        return cls._from_thing("slug_lower", slug.lower())

    @classmethod
    def _from_thing(cls, thing, value):
        assert thing in ("id", "slug_lower")
        return cls.db.one("""

            SELECT teams.*::teams
              FROM teams
             WHERE {}=%s

        """.format(thing), (value,))

    @classmethod
    def insert(cls, owner, **fields):
        fields['slug_lower'] = fields['slug'].lower()
        fields['owner'] = owner.username
        return cls.db.one("""

            INSERT INTO teams
                        (slug, slug_lower, name, homepage,
                         product_or_service, todo_url, onboarding_url,
                         owner)
                 VALUES (%(slug)s, %(slug_lower)s, %(name)s, %(homepage)s,
                         %(product_or_service)s, %(todo_url)s, %(onboarding_url)s,
                         %(owner)s)
              RETURNING teams.*::teams

        """, fields)

    def get_og_title(self):
        out = self.name
        receiving = self.receiving
        if receiving > 0:
            out += " receives $%.2f/wk" % receiving
        else:
            out += " is"
        return out + " on Gratipay"


    def update_receiving(self, cursor=None):
        r = (cursor or self.db).one("""
            WITH our_receiving AS (
                     SELECT amount
                       FROM current_payment_instructions
                       JOIN participants p ON p.username = participant
                      WHERE team = %(slug)s
                        AND p.is_suspicious IS NOT true
                        AND amount > 0
                        AND is_funded
                 )
            UPDATE teams t
               SET receiving = (COALESCE((
                       SELECT sum(amount)
                         FROM our_receiving
                   ), 0))
                 , nsupporters = COALESCE((SELECT count(*) FROM our_receiving), 0)
             WHERE t.slug = %(slug)s
         RETURNING receiving, nsupporters
        """, dict(slug=self.slug))

        self.set_attributes(receiving=r.receiving, nsupporters=r.nsupporters)

    @property
    def status(self):
        return { None: 'unreviewed'
               , False: 'rejected'
               , True: 'approved'
                }[self.is_approved]

    def migrate_tips(self):
        payment_instructions = self.db.all("""
            SELECT pi.*
              FROM payment_instructions pi
              JOIN teams t ON t.slug = pi.team
              JOIN participants p ON t.owner = p.username
             WHERE p.username = %s
               AND pi.ctime < t.ctime
        """, (self.owner, ))

        # Make sure the migration hasn't been done already
        if payment_instructions:
            raise AlreadyMigrated

        return self.db.one("""
        WITH rows AS (

            INSERT INTO payment_instructions
                        (ctime, mtime, participant, team, amount, is_funded)
                 SELECT ct.ctime
                      , ct.mtime
                      , ct.tipper
                      , %(slug)s
                      , ct.amount
                      , ct.is_funded
                   FROM current_tips ct
                   JOIN participants p ON p.username = tipper
                  WHERE ct.tippee=%(owner)s
                    AND p.claimed_time IS NOT NULL
                    AND p.is_suspicious IS NOT TRUE
                    AND p.is_closed IS NOT TRUE
              RETURNING 1

        ) SELECT count(*) FROM rows;
        """, {'slug': self.slug, 'owner': self.owner})

class AlreadyMigrated(Exception): pass
