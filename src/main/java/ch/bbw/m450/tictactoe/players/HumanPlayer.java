package ch.bbw.m450.tictactoe.players;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

import ch.bbw.m450.tictactoe.TicTacToeMain;
import ch.bbw.m450.tictactoe.TicTacToePlayer;

/**
 * Simple human-player taking input from stdin.
 */
public class HumanPlayer implements TicTacToePlayer {

	// one scanner for the whole game: a new one per move would lose input the previous one already buffered
	private final Scanner scanner;

	public HumanPlayer() {
		this(System.in);
	}

	HumanPlayer(InputStream in) {
		scanner = new Scanner(in, StandardCharsets.UTF_8);
	}

	@Override
	public int play(Stone[] board, Stone colorToPlay) {
		System.out.println(TicTacToeMain.toString(board) + "where to put the next " + colorToPlay + "? (0-8): ");
		return Integer.parseInt(scanner.nextLine());
	}
}
