"""passlib.handlers.sun_md5_crypt - Sun's Md5 Crypt, used on Solaris

.. warning::

    This implementation may not reproduce
    the original Solaris behavior in some border cases.
    See documentation for details.
"""

#=========================================================
#imports
#=========================================================
#core
from hashlib import md5
import re
import logging; log = logging.getLogger(__name__)
from warnings import warn
#site
#libs
from passlib.utils import h64, handlers as uh, to_hash_str, to_unicode, bytes, b, bord
#pkg
#local
__all__ = [
    "sun_md5_crypt",
]

#=========================================================
#backend
#=========================================================
#constant data used by alg - Hamlet act 3 scene 1 + null char
# exact bytes as in http://www.ibiblio.org/pub/docs/books/gutenberg/etext98/2ws2610.txt
# from Project Gutenberg.

MAGIC_HAMLET = b(
    "To be, or not to be,--that is the question:--\n"
    "Whether 'tis nobler in the mind to suffer\n"
    "The slings and arrows of outrageous fortune\n"
    "Or to take arms against a sea of troubles,\n"
    "And by opposing end them?--To die,--to sleep,--\n"
    "No more; and by a sleep to say we end\n"
    "The heartache, and the thousand natural shocks\n"
    "That flesh is heir to,--'tis a consummation\n"
    "Devoutly to be wish'd. To die,--to sleep;--\n"
    "To sleep! perchance to dream:--ay, there's the rub;\n"
    "For in that sleep of death what dreams may come,\n"
    "When we have shuffled off this mortal coil,\n"
    "Must give us pause: there's the respect\n"
    "That makes calamity of so long life;\n"
    "For who would bear the whips and scorns of time,\n"
    "The oppressor's wrong, the proud man's contumely,\n"
    "The pangs of despis'd love, the law's delay,\n"
    "The insolence of office, and the spurns\n"
    "That patient merit of the unworthy takes,\n"
    "When he himself might his quietus make\n"
    "With a bare bodkin? who would these fardels bear,\n"
    "To grunt and sweat under a weary life,\n"
    "But that the dread of something after death,--\n"
    "The undiscover'd country, from whose bourn\n"
    "No traveller returns,--puzzles the will,\n"
    "And makes us rather bear those ills we have\n"
    "Than fly to others that we know not of?\n"
    "Thus conscience does make cowards of us all;\n"
    "And thus the native hue of resolution\n"
    "Is sicklied o'er with the pale cast of thought;\n"
    "And enterprises of great pith and moment,\n"
    "With this regard, their currents turn awry,\n"
    "And lose the name of action.--Soft you now!\n"
    "The fair Ophelia!--Nymph, in thy orisons\n"
    "Be all my sins remember'd.\n\x00" #<- apparently null at end of C string is included (test vector won't pass otherwise)
)

#NOTE: these sequences are pre-calculated iteration ranges used by X & Y loops w/in rounds function below
xr = range(7)
_XY_ROUNDS = [
    tuple((i,i,i+3) for i in xr), #xrounds 0
    tuple((i,i+1,i+4) for i in xr), #xrounds 1
    tuple((i,i+8,(i+11)&15) for i in xr), #yrounds 0
    tuple((i,(i+9)&15, (i+12)&15) for i in xr), #yrounds 1
]
del xr

def raw_sun_md5_crypt(secret, rounds, salt):
    "given secret & salt, return encoded sun-md5-crypt checksum"
    global MAGIC_HAMLET
    assert isinstance(secret, bytes)
    assert isinstance(salt, bytes)

    #validate rounds
    if rounds <= 0:
        rounds = 0
    real_rounds = 4096 + rounds
    #NOTE: spec seems to imply max 'rounds' is 2**32-1

    #generate initial digest to start off round 0.
    #NOTE: algorithm 'salt' includes full config string w/ trailing "$"
    result = md5(secret + salt).digest()
    assert len(result) == 16

    #NOTE: many things have been inlined to speed up the loop as much as possible,
    # so that this only barely resembles the algorithm as described in the docs.
    # * all accesses to a given bit have been inlined using the formula
    #       rbitval(bit) = (rval((bit>>3) & 15) >> (bit & 7)) & 1
    # * the calculation of coinflip value R has been inlined
    # * the conditional division of coinflip value V has been inlined as a shift right of 0 or 1.
    # * the i, i+3, etc iterations are precalculated in lists.
    # * the round-based conditional division of x & y is now performed
    #   by choosing an appropriate precalculated list, so only the 7 used bits
    #   are actually calculated
    X_ROUNDS_0, X_ROUNDS_1, Y_ROUNDS_0, Y_ROUNDS_1 = _XY_ROUNDS

    #NOTE: % appears to be *slightly* slower than &, so we prefer & if possible

    round = 0
    while round < real_rounds:
        #convert last result byte string to list of byte-ints for easy access
        rval = [ bord(c) for c in result ].__getitem__

        #build up X bit by bit
        x = 0
        xrounds = X_ROUNDS_1 if (rval((round>>3) & 15)>>(round & 7)) & 1 else X_ROUNDS_0
        for i, ia, ib in xrounds:
            a = rval(ia)
            b = rval(ib)
            v = rval((a >> (b % 5)) & 15) >> ((b>>(a&7)) & 1)
            x |= ((rval((v>>3)&15)>>(v&7))&1) << i

        #build up Y bit by bit
        y = 0
        yrounds = Y_ROUNDS_1 if (rval(((round+64)>>3) & 15)>>(round & 7)) & 1 else Y_ROUNDS_0
        for i, ia, ib in yrounds:
            a = rval(ia)
            b = rval(ib)
            v = rval((a >> (b % 5)) & 15) >> ((b>>(a&7)) & 1)
            y |= ((rval((v>>3)&15)>>(v&7))&1) << i

        #extract x'th and y'th bit, xoring them together to yeild "coin flip"
        coin = ((rval(x>>3) >> (x&7)) ^ (rval(y>>3) >> (y&7))) & 1

        #construct hash for this round
        h = md5(result)
        if coin:
            h.update(MAGIC_HAMLET)
        h.update(unicode(round).encode("ascii"))
        result = h.digest()

        round += 1

    #encode output
    return h64.encode_transposed_bytes(result, _chk_offsets)

#NOTE: same offsets as md5_crypt
_chk_offsets = (
    12,6,0,
    13,7,1,
    14,8,2,
    15,9,3,
    5,10,4,
    11,
)

#=========================================================
#handler
#=========================================================
class sun_md5_crypt(uh.HasRounds, uh.HasSalt, uh.GenericHandler):
    """This class implements the Sun-MD5-Crypt password hash, and follows the :ref:`password-hash-api`.

    It supports a variable-length salt, and a variable number of rounds.

    The :meth:`encrypt()` and :meth:`genconfig` methods accept the following optional keywords:

    :param salt:
        Optional salt string.
        If not specified, a salt will be autogenerated (this is recommended).
        If specified, it must be drawn from the regexp range ``[./0-9A-Za-z]``.

    :param salt_size:
        If no salt is specified, this parameter can be used to specify
        the size (in characters) of the autogenerated salt.
        It currently defaults to 8.

    :param rounds:
        Optional number of rounds to use.
        Defaults to 5000, must be between 0 and 4294963199, inclusive.

    :param bare_salt:
        Optional flag used to enable an alternate salt digest behavior
        used by some hash strings in this scheme.
        This flag can be ignored by most users.
        Defaults to ``False``.
        (see :ref:`smc-bare-salt` for details).
    """
    #=========================================================
    #class attrs
    #=========================================================
    name = "sun_md5_crypt"
    setting_kwds = ("salt", "rounds", "bare_salt", "salt_size")
    checksum_chars = uh.H64_CHARS

    #NOTE: docs say max password length is 255.
    #release 9u2

    #NOTE: not sure if original crypt has a salt size limit,
    # all instances that have been seen use 8 chars.
    default_salt_size = 8
    min_salt_size = 0
    max_salt_size = None
    salt_chars = uh.H64_CHARS

    default_rounds = 5000 #current passlib default
    min_rounds = 0
    max_rounds = 4294963199 ##2**32-1-4096
        #XXX: ^ not sure what it does if past this bound... does 32 int roll over?
    rounds_cost = "linear"
    _strict_rounds_bounds = True

    #=========================================================
    #instance attrs
    #=========================================================
    bare_salt = False #flag to indicate legacy hashes that lack "$$" suffix

    #=========================================================
    #constructor
    #=========================================================
    def __init__(self, bare_salt=False, **kwds):
        self.bare_salt = bare_salt
        super(sun_md5_crypt, self).__init__(**kwds)

    #=========================================================
    #internal helpers
    #=========================================================
    @classmethod
    def identify(cls, hash):
        return uh.identify_prefix(hash, (u"$md5$", u"$md5,"))

    @classmethod
    def from_string(cls, hash):
        if not hash:
            raise ValueError("no hash specified")
        if isinstance(hash, bytes):
            hash = hash.decode("ascii")

        #
        #detect if hash specifies rounds value.
        #if so, parse and validate it.
        #by end, set 'rounds' to int value, and 'tail' containing salt+chk
        #
        if hash.startswith(u"$md5$"):
            rounds = 0
            salt_idx = 5
        elif hash.startswith(u"$md5,rounds="):
            idx = hash.find(u"$", 12)
            if idx == -1:
                raise ValueError("invalid sun-md5-crypt hash (unexpected end of rounds)")
            rstr = hash[12:idx]
            try:
                rounds = int(rstr)
            except ValueError:
                raise ValueError("invalid sun-md5-crypt hash (bad rounds)")
            if rstr != unicode(rounds):
                raise ValueError("invalid sun-md5-crypt hash (zero-padded rounds)")
            if rounds == 0:
                #NOTE: not sure if this is *forbidden* precisely,
                #      but allowing it would complicate things,
                #      and it should never occur anyways.
                raise ValueError("invalid sun-md5-crypt hash (explicit zero rounds)")
            salt_idx = idx+1
        else:
            raise ValueError("invalid sun-md5-crypt hash (unknown prefix)")

        #
        #salt/checksum separation is kinda weird,
        #to deal cleanly with some backward-compatible workarounds
        #implemented by original implementation.
        #
        chk_idx = hash.rfind(u"$", salt_idx)
        if chk_idx == -1:
            # ''-config for $-hash
            salt = hash[salt_idx:]
            chk = None
            bare_salt = True
        elif chk_idx == len(hash)-1:
            if chk_idx > salt_idx and hash[-2] == u"$":
                raise ValueError("invalid sun-md5-crypt hash (too many $)")
            # $-config for $$-hash
            salt = hash[salt_idx:-1]
            chk = None
            bare_salt = False
        elif chk_idx > 0 and hash[chk_idx-1] == u"$":
            # $$-hash
            salt = hash[salt_idx:chk_idx-1]
            chk = hash[chk_idx+1:]
            bare_salt = False
        else:
            # $-hash
            salt = hash[salt_idx:chk_idx]
            chk = hash[chk_idx+1:]
            bare_salt = True

        return cls(
            rounds=rounds,
            salt=salt,
            checksum=chk,
            bare_salt=bare_salt,
            strict=bool(chk),
        )

    def to_string(self, withchk=True, native=True):
        ss = u'' if self.bare_salt else u'$'
        rounds = self.rounds
        if rounds > 0:
            out = u"$md5,rounds=%d$%s%s" % (rounds, self.salt, ss)
        else:
            out = u"$md5$%s%s" % (self.salt, ss)
        if withchk:
            chk = self.checksum
            if chk:
                out = u"%s$%s" % (out, chk)
        return to_hash_str(out) if native else out

    #=========================================================
    #primary interface
    #=========================================================
    #TODO: if we're on solaris, check for native crypt() support.
    # this will require extra testing, to make sure native crypt
    # actually behaves correctly.
    # especially, when using ''-config, make sure to append '$x' to string.

    def calc_checksum(self, secret):
        #NOTE: no reference for how sun_md5_crypt handles unicode
        if secret is None:
            raise TypeError("no secret specified")
        if isinstance(secret, unicode):
            secret = secret.encode("utf-8")
        config = self.to_string(withchk=False,native=False).encode("ascii")
        return raw_sun_md5_crypt(secret, self.rounds, config).decode("ascii")

    #=========================================================
    #eoc
    #=========================================================

#=========================================================
#eof
#=========================================================
