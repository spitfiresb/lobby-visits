# Note to Dana

Hi Dana,

The Front Desk is ready to try. You, Marcus and Ines see everything. Sam, Priya, Jonas, Ruth and Kenji see how busy the lobby is, but never who visited. Nobody else can get in. To see who came in last Tuesday, set both dates to that day. Below is what I found in the two files, what I decided about access, and what's still missing.

## What I found in the data

None of the files were changed. The app cleans them as it loads.

- **Two of your three admins would have been locked out.** In the user list, Marcus's email has capital letters and Ines's has spaces around it. The app now ignores capitals and spaces when it matches emails, both in the list and in what people type.
- **58 sign-ins were recorded twice.** They're all at the end of the export. Each repeats a real sign-in from 11 to 95 seconds earlier, with the same visitor, host and visit type. It looks like a double tap on the iPad. Left in, they would make every count about 3% too high. The app keeps the first sign-in and ignores a repeat within 5 minutes, so the 2,011 rows become 1,953 visits. Three people really did come back later the same day, and they're kept.
- **The iPad recorded nothing from Monday 10 to Thursday 13 August.** Friday the 14th has 20 visits, so this looks like an outage rather than four quiet days. That matters for the busiest day: the gap takes a day away from Monday to Thursday but not from Friday. So instead of comparing totals, the app compares the average for each weekday over the days that were recorded. On that basis **Tuesday is the busiest day, with 39.6 visits a day, just ahead of Wednesday's 39.2**. Plain totals would have said Wednesday. Honestly, those two are too close to call. The pattern you can rely on is that midweek is busy, and Mondays and Fridays are quiet (a Friday has about half the visitors of a Tuesday). The page warns you whenever your dates include the gap. Do you know what happened that week?
- **The busiest hour is 9 to 10 am,** with more than a third of all sign-ins.
- **Almost half of visitors (45%) never sign out.** That's spread evenly across months and visit types, so it's normal behaviour, not a fault. The app says "Didn't sign out", and no number depends on how long a visit lasted.

## Access decisions

- **Viewers never receive names.** For a viewer, the server leaves the visitor's name, email and company, and the host's name, out of what it sends. They aren't hidden on the page. They're never sent, so a viewer can't find them by editing the address or looking at what their browser received.
- **What a viewer sees instead:** a grey "Visitor" in the list. On a visit's own page, the heading is the visit type, such as "Interview visit", with a line saying names are only shown to admins. They still see the date, the times, the visit type, the host team and whether the visit was pre-registered.
- **Viewers don't see the visitor's company or the host's name either.** You listed those as admin information, and a company plus a date is often enough to work out who came in.
- **Search is for admins only.** Otherwise a viewer could type a name and find out whether that person visited, without ever seeing it.
- **Someone not on the list is told:** "This email isn't on the list of people who can use The Front Desk. Check it for typos, or ask Brightline's workplace team for access." I chose the friendly version because the people most likely to see it are colleagues who mistyped their email. The cost is that a stranger can check whether an email is on the list. I think that's acceptable: they still can't get in, and the sign-in page gives the same answer for a wrong email and a wrong password.

## What's fake about the sign-in

It's a prototype. Accounts and sign-ins are kept in the server's memory, so a restart forgets everyone, and each person has to sign up again. Signing up doesn't check that you own the email, so anyone who knows a listed colleague's address could register as them before they do. Passwords are stored scrambled (hashed), never as typed. There's no password reset or two-step sign-in, and a sign-in lasts until you close the browser.

## What I'd do differently with real visitors' data

People would sign in with Brightline's existing company login instead of a password made for this app, so we'd know they own their email, and sign-ins would time out. It would run on a secure (HTTPS) server with a proper database. I'd keep a record of which admin opened which visitor's details. I'd also agree with legal how long names are kept: counts can stay, but names probably shouldn't stay forever. And I'd fix the double tap on the iPad itself, with an alert if it stops recording again.

## What's next, and what was dropped

Nothing was dropped. Sign-up, sign-in, the visit list with its filters and busiest day and hour, a page for each visit, the user list for admins and a "page not found" page are all there. The visit list also filters by host team, pre-registered and signed out. Next, in order:

1. Keep accounts when the server restarts.
2. Your answer about 10 to 13 August, in case it changes how we read those weeks.
3. Company sign-in and a record of who viewed what, before any real visitor data goes in.

Zain
