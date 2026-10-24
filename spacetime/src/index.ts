// Niche live state. FastAPI does the heavy work (Claude, Apify, Stripe) and writes results here through
// service-only reducers; browsers subscribe to the public tables and call the moodboard reducers directly.
import { schema, table, t, SenderError, type InferSchema, type ReducerCtx } from 'spacetimedb/server';

// Identities allowed to call service reducers. Seeded with the publisher in `init`; the FastAPI backend
// connects with that identity's token (see spacetime/README.md).
const service = table({ name: 'service' }, { identity: t.identity().primaryKey() });

// Where each moodboard piece has been dragged, shared by everyone viewing the board (keyed by profile id).
const boardPiece = table(
  { name: 'board_piece', public: true },
  {
    key: t.string().primaryKey(), // `${boardId}:${pieceId}`
    boardId: t.string().index('btree'),
    pieceId: t.string(),
    dx: t.f64(),
    dy: t.f64(),
    z: t.u32(),
    movedBy: t.identity(),
    updatedAt: t.timestamp(),
  }
);

// Live cursors of people looking at a board together.
const boardCursor = table(
  { name: 'board_cursor', public: true },
  {
    key: t.string().primaryKey(), // `${boardId}:${identity hex}`
    boardId: t.string().index('btree'),
    viewer: t.identity().index('btree'),
    name: t.string(),
    color: t.string(),
    x: t.f64(),
    y: t.f64(),
    updatedAt: t.timestamp(),
  }
);

// Progress of a taste-profile build, so the UI can show it instead of a blind spinner.
const buildProgress = table(
  { name: 'build_progress', public: true },
  {
    profileId: t.string().primaryKey(),
    stage: t.string(), // extracting | clustering | done | failed
    done: t.u32(),
    total: t.u32(),
    message: t.string(),
    updatedAt: t.timestamp(),
  }
);

// Bumped whenever a profile changes (build, typed or spoken edit) so open pages refetch it.
const profileVersion = table(
  { name: 'profile_version', public: true },
  {
    profileId: t.string().primaryKey(),
    version: t.u32(),
    updatedAt: t.timestamp(),
  }
);

const search = table(
  { name: 'search', public: true },
  {
    searchId: t.string().primaryKey(),
    profileId: t.string().index('btree'),
    query: t.string(),
    status: t.string(),
    rankingMethod: t.string(),
    warnings: t.array(t.string()),
    updatedAt: t.timestamp(),
  }
);

// Listings stream in per marketplace as soon as each source finishes; ranking later fills in score/reason.
const listing = table(
  { name: 'listing', public: true },
  {
    key: t.string().primaryKey(), // `${searchId}:${listingId}`
    searchId: t.string().index('btree'),
    listingId: t.string(),
    source: t.string(),
    title: t.string(),
    url: t.string(),
    imageUrl: t.string(),
    price: t.f64(),
    currency: t.string(),
    seller: t.string(),
    reason: t.string(),
    warnings: t.array(t.string()),
    score: t.option(t.f64()),
    rank: t.option(t.u32()),
    isFixture: t.bool(),
    updatedAt: t.timestamp(),
  }
);

const spacetimedb = schema({ service, boardPiece, boardCursor, buildProgress, profileVersion, search, listing });
export default spacetimedb;

type Ctx = ReducerCtx<InferSchema<typeof spacetimedb>>;

function requireService(ctx: Ctx) {
  if (!ctx.db.service.identity.find(ctx.sender)) throw new SenderError('service only');
}

function requireBoard(boardId: string) {
  if (!boardId || boardId.length > 64) throw new SenderError('invalid board');
}

export const init = spacetimedb.init((ctx) => {
  ctx.db.service.insert({ identity: ctx.sender });
});

export const onDisconnect = spacetimedb.clientDisconnected((ctx) => {
  for (const cursor of [...ctx.db.boardCursor.viewer.filter(ctx.sender)]) ctx.db.boardCursor.key.delete(cursor.key);
});

// ---- Moodboard (any viewer holding the board id, i.e. the share link) ----

export const movePiece = spacetimedb.reducer(
  { boardId: t.string(), pieceId: t.string(), dx: t.f64(), dy: t.f64(), z: t.u32() },
  (ctx, { boardId, pieceId, dx, dy, z }) => {
    requireBoard(boardId);
    if (!pieceId || pieceId.length > 128 || !Number.isFinite(dx) || !Number.isFinite(dy)) {
      throw new SenderError('invalid piece');
    }
    const key = `${boardId}:${pieceId}`;
    const row = { key, boardId, pieceId, dx, dy, z, movedBy: ctx.sender, updatedAt: ctx.timestamp };
    if (ctx.db.boardPiece.key.find(key)) ctx.db.boardPiece.key.update(row);
    else ctx.db.boardPiece.insert(row);
  }
);

export const resetBoard = spacetimedb.reducer({ boardId: t.string() }, (ctx, { boardId }) => {
  requireBoard(boardId);
  for (const piece of [...ctx.db.boardPiece.boardId.filter(boardId)]) ctx.db.boardPiece.key.delete(piece.key);
});

export const moveCursor = spacetimedb.reducer(
  { boardId: t.string(), name: t.string(), color: t.string(), x: t.f64(), y: t.f64() },
  (ctx, { boardId, name, color, x, y }) => {
    requireBoard(boardId);
    const key = `${boardId}:${ctx.sender.toHexString()}`;
    const row = {
      key,
      boardId,
      viewer: ctx.sender,
      name: name.slice(0, 40),
      color: color.slice(0, 16),
      x,
      y,
      updatedAt: ctx.timestamp,
    };
    if (ctx.db.boardCursor.key.find(key)) ctx.db.boardCursor.key.update(row);
    else ctx.db.boardCursor.insert(row);
  }
);

export const leaveBoard = spacetimedb.reducer({ boardId: t.string() }, (ctx, { boardId }) => {
  ctx.db.boardCursor.key.delete(`${boardId}:${ctx.sender.toHexString()}`);
});

// ---- Service-only: written by the FastAPI backend ----

export const setBuildProgress = spacetimedb.reducer(
  { profileId: t.string(), stage: t.string(), done: t.u32(), total: t.u32(), message: t.string() },
  (ctx, args) => {
    requireService(ctx);
    const row = { ...args, updatedAt: ctx.timestamp };
    if (ctx.db.buildProgress.profileId.find(args.profileId)) ctx.db.buildProgress.profileId.update(row);
    else ctx.db.buildProgress.insert(row);
  }
);

export const setProfileVersion = spacetimedb.reducer(
  { profileId: t.string(), version: t.u32() },
  (ctx, { profileId, version }) => {
    requireService(ctx);
    const row = { profileId, version, updatedAt: ctx.timestamp };
    if (ctx.db.profileVersion.profileId.find(profileId)) ctx.db.profileVersion.profileId.update(row);
    else ctx.db.profileVersion.insert(row);
  }
);

export const upsertSearch = spacetimedb.reducer(
  {
    searchId: t.string(),
    profileId: t.string(),
    query: t.string(),
    status: t.string(),
    rankingMethod: t.string(),
    warnings: t.array(t.string()),
  },
  (ctx, args) => {
    requireService(ctx);
    const row = { ...args, updatedAt: ctx.timestamp };
    if (ctx.db.search.searchId.find(args.searchId)) ctx.db.search.searchId.update(row);
    else ctx.db.search.insert(row);
  }
);

const ListingInput = t.object('ListingInput', {
  listingId: t.string(),
  source: t.string(),
  title: t.string(),
  url: t.string(),
  imageUrl: t.string(),
  price: t.f64(),
  currency: t.string(),
  seller: t.string(),
  reason: t.string(),
  warnings: t.array(t.string()),
  score: t.option(t.f64()),
  rank: t.option(t.u32()),
  isFixture: t.bool(),
});

export const upsertListings = spacetimedb.reducer(
  { searchId: t.string(), listings: t.array(ListingInput), replace: t.bool() },
  (ctx, { searchId, listings, replace }) => {
    requireService(ctx);
    // `replace` swaps the provisional per-source rows for the final ranked set in one transaction.
    if (replace) {
      for (const row of [...ctx.db.listing.searchId.filter(searchId)]) ctx.db.listing.key.delete(row.key);
    }
    for (const item of listings) {
      const key = `${searchId}:${item.listingId}`;
      const row = { ...item, key, searchId, updatedAt: ctx.timestamp };
      if (ctx.db.listing.key.find(key)) ctx.db.listing.key.update(row);
      else ctx.db.listing.insert(row);
    }
  }
);
